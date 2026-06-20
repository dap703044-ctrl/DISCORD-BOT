import os
import sys
import json
import sqlite3
import asyncio
import random
from threading import Thread
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

import nextcord
from nextcord import Interaction, SlashOption, Embed, ButtonStyle
from nextcord.ext import commands, tasks
from nextcord.ui import View, Button, Modal, TextInput

from flask import Flask, jsonify
from dotenv import load_dotenv

load_dotenv()

# ===== CONFIG =====
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("❌ DISCORD_TOKEN not set!")
    sys.exit(1)

# ===== DATABASE (SQLite - No PostgreSQL needed!) =====
DB_PATH = "bot_data.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Guilds
    c.execute('''CREATE TABLE IF NOT EXISTS guilds (
        id INTEGER PRIMARY KEY,
        name TEXT,
        owner_id INTEGER,
        welcome_channel INTEGER,
        mod_log INTEGER,
        level_channel INTEGER,
        announcement_channel INTEGER,
        config TEXT
    )''')
    
    # Members
    c.execute('''CREATE TABLE IF NOT EXISTS members (
        user_id INTEGER,
        guild_id INTEGER,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 1,
        messages INTEGER DEFAULT 0,
        warnings INTEGER DEFAULT 0,
        PRIMARY KEY (user_id, guild_id)
    )''')
    
    # Warnings
    c.execute('''CREATE TABLE IF NOT EXISTS warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        guild_id INTEGER,
        moderator_id INTEGER,
        reason TEXT,
        timestamp TEXT,
        expires TEXT,
        is_active INTEGER DEFAULT 1
    )''')
    
    # Global Bans
    c.execute('''CREATE TABLE IF NOT EXISTS global_bans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        reason TEXT,
        issuer_id INTEGER,
        timestamp TEXT,
        is_active INTEGER DEFAULT 1
    )''')
    
    # Events
    c.execute('''CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        title TEXT,
        description TEXT,
        location TEXT,
        start_time TEXT,
        organizer_id INTEGER,
        max_participants INTEGER DEFAULT 0,
        participants TEXT,
        status TEXT DEFAULT 'upcoming'
    )''')
    
    # Announcements
    c.execute('''CREATE TABLE IF NOT EXISTS announcements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id INTEGER,
        author_id INTEGER,
        title TEXT,
        content TEXT,
        image_url TEXT,
        timestamp TEXT,
        is_global INTEGER DEFAULT 0
    )''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

init_db()

# ===== DATABASE FUNCTIONS =====
def get_guild(guild_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM guilds WHERE id = ?", (guild_id,))
    result = c.fetchone()
    conn.close()
    if not result:
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO guilds (id, config) VALUES (?, ?)", (guild_id, "{}"))
        conn.commit()
        conn.close()
        return get_guild(guild_id)
    return result

def update_guild(guild_id, **kwargs):
    conn = get_db()
    c = conn.cursor()
    for key, value in kwargs.items():
        c.execute(f"UPDATE guilds SET {key} = ? WHERE id = ?", (value, guild_id))
    conn.commit()
    conn.close()

def get_member(user_id, guild_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM members WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    result = c.fetchone()
    conn.close()
    if not result:
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO members (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))
        conn.commit()
        conn.close()
        return get_member(user_id, guild_id)
    return result

def add_xp(user_id, guild_id, amount):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE members SET xp = xp + ?, messages = messages + 1 WHERE user_id = ? AND guild_id = ?", (amount, user_id, guild_id))
    c.execute("SELECT xp, level FROM members WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    row = c.fetchone()
    xp = row[0]
    level = row[1]
    level_up = False
    while xp >= level * 100:
        xp -= level * 100
        level += 1
        level_up = True
    c.execute("UPDATE members SET xp = ?, level = ? WHERE user_id = ? AND guild_id = ?", (xp, level, user_id, guild_id))
    conn.commit()
    conn.close()
    return level, level_up

def add_warning(user_id, guild_id, moderator_id, reason, expires=None):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO warnings (user_id, guild_id, moderator_id, reason, timestamp, expires) VALUES (?, ?, ?, ?, ?, ?)",
              (user_id, guild_id, moderator_id, reason, datetime.now().isoformat(), expires))
    c.execute("UPDATE members SET warnings = warnings + 1 WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    conn.commit()
    conn.close()

def get_warnings(user_id, guild_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM warnings WHERE user_id = ? AND guild_id = ? AND is_active = 1 ORDER BY timestamp DESC", (user_id, guild_id))
    result = c.fetchall()
    conn.close()
    return result

def add_global_ban(user_id, reason, issuer_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO global_bans (user_id, reason, issuer_id, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, reason, issuer_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def remove_global_ban(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE global_bans SET is_active = 0 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def is_globally_banned(user_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM global_bans WHERE user_id = ? AND is_active = 1", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def create_event(guild_id, title, description, location, organizer_id, max_participants=0):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO events (guild_id, title, description, location, start_time, organizer_id, max_participants, participants) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
              (guild_id, title, description, location, datetime.now().isoformat(), organizer_id, max_participants, json.dumps([])))
    conn.commit()
    conn.close()

def get_events(guild_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM events WHERE guild_id = ? AND status = 'upcoming' ORDER BY start_time", (guild_id,))
    result = c.fetchall()
    conn.close()
    return result

def add_announcement(guild_id, author_id, title, content, image_url=None, is_global=0):
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO announcements (guild_id, author_id, title, content, image_url, timestamp, is_global) VALUES (?, ?, ?, ?, ?, ?, ?)",
              (guild_id, author_id, title, content, image_url, datetime.now().isoformat(), is_global))
    conn.commit()
    conn.close()

# ===== BOT =====
intents = nextcord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

# ===== UI COMPONENTS =====
class ConfirmView(View):
    def __init__(self, timeout=60):
        super().__init__(timeout=timeout)
        self.value = None
    
    @nextcord.ui.button(label="✅ Confirm", style=ButtonStyle.green)
    async def confirm(self, button, interaction):
        self.value = True
        self.stop()
        await interaction.response.send_message("✅ Confirmed!", ephemeral=True)
    
    @nextcord.ui.button(label="❌ Cancel", style=ButtonStyle.red)
    async def cancel(self, button, interaction):
        self.value = False
        self.stop()
        await interaction.response.send_message("❌ Cancelled!", ephemeral=True)

class WarningModal(Modal):
    def __init__(self, member):
        super().__init__(title=f"⚠️ Warn {member.display_name}")
        self.member = member
        self.reason = TextInput(label="Reason", placeholder="Enter reason...", style=TextInputStyle.paragraph, required=True)
        self.duration = TextInput(label="Duration (hours, optional)", placeholder="Leave empty for permanent", required=False)
        self.add_item(self.reason)
        self.add_item(self.duration)

class AnnouncementModal(Modal):
    def __init__(self):
        super().__init__(title="📢 Announcement")
        self.title = TextInput(label="Title", placeholder="Title...", required=True)
        self.content = TextInput(label="Content", placeholder="Content...", style=TextInputStyle.paragraph, required=True)
        self.image = TextInput(label="Image URL (optional)", placeholder="https://...", required=False)
        self.add_item(self.title)
        self.add_item(self.content)
        self.add_item(self.image)

# ===== EVENTS =====
@bot.event
async def on_ready():
    print(f"✅ Bot connected as {bot.user}")
    print(f"🌍 Connected to {len(bot.guilds)} servers")
    await bot.change_presence(activity=nextcord.Activity(type=nextcord.ActivityType.watching, name="🇷🇴 România | /help"))
    try:
        await bot.sync_application_commands()
        print("✅ Slash commands synced")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    if message.guild:
        level, level_up = add_xp(message.author.id, message.guild.id, random.randint(5, 20))
        if level_up:
            embed = Embed(title="🎉 Level Up!", description=f"{message.author.mention} reached **Level {level}!**", color=0x57F287)
            await message.channel.send(embed=embed)
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    guild_data = get_guild(member.guild.id)
    if guild_data["welcome_channel"]:
        channel = bot.get_channel(guild_data["welcome_channel"])
        if channel:
            embed = Embed(title=f"🇷🇴 Welcome to {member.guild.name}!", description=f"Salut {member.mention}!\nSpune-ne de unde ești?", color=0xF1C40F)
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(embed=embed)

# ===== SLASH COMMANDS =====

# ----- BASIC -----
@bot.slash_command(name="ping", description="🏓 Check bot latency")
async def ping(interaction: Interaction):
    await interaction.response.send_message(f"🏓 Pong! Latency: **{round(bot.latency * 1000)}ms**")

@bot.slash_command(name="help", description="📖 Show all commands")
async def help_command(interaction: Interaction):
    embed = Embed(title="📖 Commands", color=0x5865F2)
    embed.add_field(name="🛡️ Moderation", value="/clear, /kick, /ban, /warn, /warnings, /mute", inline=False)
    embed.add_field(name="📊 Leveling", value="/rank, /leaderboard", inline=False)
    embed.add_field(name="📢 Announcements", value="/announce", inline=False)
    embed.add_field(name="🎪 Events", value="/event_create, /events", inline=False)
    embed.add_field(name="🌍 Global (GM Only)", value="/global_ban, /global_unban, /global_announce, /global_dm, /global_kick", inline=False)
    embed.add_field(name="⚙️ Setup", value="/setup", inline=False)
    embed.set_footer(text="🇷🇴 Romanian Oversight Bot")
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="server", description="📊 Server information")
async def server_info(interaction: Interaction):
    guild = interaction.guild
    embed = Embed(title=f"📊 {guild.name}", color=0x5865F2)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="👥 Members", value=f"**{guild.member_count}**", inline=True)
    embed.add_field(name="💬 Channels", value=f"**{len(guild.channels)}**", inline=True)
    embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=False)
    await interaction.response.send_message(embed=embed)

# ----- LEVELING -----
@bot.slash_command(name="rank", description="🎯 Check your level")
async def rank(interaction: Interaction, member: nextcord.Member = SlashOption(description="Member to check", required=False)):
    if not member:
        member = interaction.user
    data = get_member(member.id, interaction.guild_id)
    embed = Embed(title=f"👤 {member.display_name}'s Profile", color=member.color.value if member.color else 0x5865F2)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="📊 Level", value=f"**{data['level']}**", inline=True)
    embed.add_field(name="⭐ XP", value=f"**{data['xp']}**", inline=True)
    embed.add_field(name="💬 Messages", value=f"**{data['messages']}**", inline=True)
    embed.add_field(name="⚠️ Warnings", value=f"**{data['warnings']}**", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="leaderboard", description="🏆 Server leaderboard")
async def leaderboard(interaction: Interaction):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT user_id, level, xp FROM members WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10", (interaction.guild_id,))
    results = c.fetchall()
    conn.close()
    embed = Embed(title=f"🏆 Leaderboard - {interaction.guild.name}", color=0xF1C40F)
    for i, row in enumerate(results, 1):
        user = interaction.guild.get_member(row[0])
        if user:
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
            embed.add_field(name=f"{emoji} {user.display_name}", value=f"Level **{row[1]}** - {row[2]} XP", inline=False)
    await interaction.response.send_message(embed=embed)

# ----- MODERATION -----
@bot.slash_command(name="clear", description="🧹 Clear messages")
@commands.has_permissions(manage_messages=True)
async def clear(interaction: Interaction, amount: int = SlashOption(description="Number of messages", min_value=1, max_value=100, required=True)):
    await interaction.response.defer()
    deleted = await interaction.channel.purge(limit=amount)
    embed = Embed(title="✅ Cleared", description=f"**{len(deleted)}** messages deleted", color=0x57F287)
    await interaction.followup.send(embed=embed)

@bot.slash_command(name="kick", description="👢 Kick a member")
@commands.has_permissions(kick_members=True)
async def kick(interaction: Interaction, member: nextcord.Member = SlashOption(description="Member", required=True), reason: str = SlashOption(description="Reason", required=False)):
    if member == interaction.user:
        return await interaction.response.send_message(embed=Embed(title="❌ Error", description="You can't kick yourself!", color=0xED4245))
    await member.kick(reason=reason or "No reason")
    embed = Embed(title="✅ Kicked", description=f"{member.mention} was kicked", color=0x57F287)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="ban", description="🔨 Ban a member")
@commands.has_permissions(ban_members=True)
async def ban(interaction: Interaction, member: nextcord.Member = SlashOption(description="Member", required=True), reason: str = SlashOption(description="Reason", required=False)):
    if member == interaction.user:
        return await interaction.response.send_message(embed=Embed(title="❌ Error", description="You can't ban yourself!", color=0xED4245))
    await member.ban(reason=reason or "No reason")
    embed = Embed(title="✅ Banned", description=f"{member.mention} was banned", color=0x57F287)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="warn", description="⚠️ Warn a member")
@commands.has_permissions(moderate_members=True)
async def warn(interaction: Interaction, member: nextcord.Member = SlashOption(description="Member", required=True)):
    modal = WarningModal(member)
    await interaction.response.send_modal(modal)
    await modal.wait()
    if modal.is_finished():
        reason = modal.reason.value
        duration = modal.duration.value
        expires = None
        if duration and duration.isdigit():
            expires = (datetime.now() + timedelta(hours=int(duration))).isoformat()
        add_warning(member.id, interaction.guild_id, interaction.user.id, reason, expires)
        embed = Embed(title="⚠️ Warning Issued", description=f"{member.mention} was warned\n**Reason:** {reason}", color=0xFEE75C)
        await interaction.channel.send(embed=embed)

@bot.slash_command(name="warnings", description="⚠️ View warnings for a member")
@commands.has_permissions(moderate_members=True)
async def warnings(interaction: Interaction, member: nextcord.Member = SlashOption(description="Member", required=True)):
    warnings_list = get_warnings(member.id, interaction.guild_id)
    if not warnings_list:
        embed = Embed(title="✅ No Warnings", description=f"{member.mention} has no warnings", color=0x57F287)
        return await interaction.response.send_message(embed=embed)
    embed = Embed(title=f"⚠️ Warnings for {member.display_name}", description=f"Total: {len(warnings_list)}", color=0xFEE75C)
    for i, w in enumerate(warnings_list[:5], 1):
        mod = interaction.guild.get_member(w["moderator_id"])
        embed.add_field(name=f"Warning #{i}", value=f"Reason: {w['reason']}\nModerator: {mod.mention if mod else 'Unknown'}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="mute", description="🔇 Mute a member")
@commands.has_permissions(moderate_members=True)
async def mute(interaction: Interaction, member: nextcord.Member = SlashOption(description="Member", required=True), duration: int = SlashOption(description="Minutes", min_value=1, max_value=40320, required=True), reason: str = SlashOption(description="Reason", required=False)):
    if member == interaction.user:
        return await interaction.response.send_message(embed=Embed(title="❌ Error", description="You can't mute yourself!", color=0xED4245))
    await member.timeout(timedelta(minutes=duration), reason=reason or "No reason")
    embed = Embed(title="✅ Muted", description=f"{member.mention} muted for {duration} minutes", color=0x57F287)
    await interaction.response.send_message(embed=embed)

# ----- ANNOUNCEMENTS -----
@bot.slash_command(name="announce", description="📢 Create announcement")
@commands.has_permissions(administrator=True)
async def announce(interaction: Interaction):
    modal = AnnouncementModal()
    await interaction.response.send_modal(modal)
    await modal.wait()
    if modal.is_finished():
        embed = Embed(title=f"📢 {modal.title.value}", description=modal.content.value, color=0xF1C40F)
        if modal.image.value:
            embed.set_image(url=modal.image.value)
        guild_data = get_guild(interaction.guild_id)
        channel_id = guild_data["announcement_channel"]
        if channel_id:
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(embed=embed)
                await interaction.channel.send(embed=Embed(title="✅ Sent", description=f"Announcement sent to {channel.mention}", color=0x57F287))
                return
        await interaction.channel.send(embed=embed)

# ----- EVENTS -----
@bot.slash_command(name="event_create", description="🎪 Create an event")
@commands.has_permissions(administrator=True)
async def event_create(interaction: Interaction, title: str = SlashOption(description="Event title", required=True), description: str = SlashOption(description="Event description", required=True), location: str = SlashOption(description="Location", required=True), max_participants: int = SlashOption(description="Max participants", required=False)):
    create_event(interaction.guild_id, title, description, location, interaction.user.id, max_participants or 0)
    embed = Embed(title="🎪 Event Created", description=f"**{title}**\n{description}\n📍 {location}", color=0x1ABC9C)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="events", description="📋 List upcoming events")
async def events(interaction: Interaction):
    events_list = get_events(interaction.guild_id)
    if not events_list:
        embed = Embed(title="📋 No Events", description="No upcoming events", color=0x5865F2)
        return await interaction.response.send_message(embed=embed)
    embed = Embed(title=f"📋 Upcoming Events - {interaction.guild.name}", color=0x1ABC9C)
    for event in events_list[:5]:
        organizer = interaction.guild.get_member(event["organizer_id"])
        embed.add_field(name=event["title"], value=f"📍 {event['location']}\n👤 {organizer.mention if organizer else 'Unknown'}", inline=False)
    await interaction.response.send_message(embed=embed)

# ----- GLOBAL COMMANDS (GM Only) -----
@bot.slash_command(name="global_ban", description="🌍 Ban a user from ALL servers (GM only)")
@commands.is_owner()
async def global_ban(interaction: Interaction, user_id: str = SlashOption(description="User ID", required=True), reason: str = SlashOption(description="Reason", required=True)):
    await interaction.response.defer()
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
    except:
        return await interaction.followup.send(embed=Embed(title="❌ Error", description="Invalid user ID", color=0xED4245))
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Confirm Global Ban", description=f"Ban {user.mention} from ALL {len(bot.guilds)} servers?\nReason: {reason}", color=0xFEE75C)
    await interaction.followup.send(embed=embed, view=view)
    await view.wait()
    if not view.value:
        return
    
    add_global_ban(user_id, reason, interaction.user.id)
    count = 0
    for guild in bot.guilds:
        try:
            member = await guild.fetch_member(user_id)
            await guild.ban(member, reason=f"🌍 Global Ban: {reason}")
            count += 1
        except:
            pass
    
    embed = Embed(title="✅ Global Ban Complete", description=f"{user.mention} banned from {count} servers", color=0x57F287)
    await interaction.channel.send(embed=embed)

@bot.slash_command(name="global_unban", description="🌍 Remove global ban (GM only)")
@commands.is_owner()
async def global_unban(interaction: Interaction, user_id: str = SlashOption(description="User ID", required=True)):
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
    except:
        return await interaction.response.send_message(embed=Embed(title="❌ Error", description="Invalid user ID", color=0xED4245))
    
    remove_global_ban(user_id)
    count = 0
    for guild in bot.guilds:
        try:
            await guild.unban(user)
            count += 1
        except:
            pass
    
    embed = Embed(title="✅ Global Unban Complete", description=f"{user.mention} unbanned from {count} servers", color=0x57F287)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="global_kick", description="👢 Kick a user from ALL servers (GM only)")
@commands.is_owner()
async def global_kick(interaction: Interaction, user_id: str = SlashOption(description="User ID", required=True), reason: str = SlashOption(description="Reason", required=True)):
    await interaction.response.defer()
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
    except:
        return await interaction.followup.send(embed=Embed(title="❌ Error", description="Invalid user ID", color=0xED4245))
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Confirm Global Kick", description=f"Kick {user.mention} from ALL {len(bot.guilds)} servers?\nReason: {reason}", color=0xFEE75C)
    await interaction.followup.send(embed=embed, view=view)
    await view.wait()
    if not view.value:
        return
    
    count = 0
    for guild in bot.guilds:
        try:
            member = await guild.fetch_member(user_id)
            await guild.kick(member, reason=f"🌍 Global Kick: {reason}")
            count += 1
        except:
            pass
    
    embed = Embed(title="✅ Global Kick Complete", description=f"{user.mention} kicked from {count} servers", color=0x57F287)
    await interaction.channel.send(embed=embed)

@bot.slash_command(name="global_announce", description="🌍 Send announcement to ALL servers (GM only)")
@commands.is_owner()
async def global_announce(interaction: Interaction, title: str = SlashOption(description="Title", required=True), content: str = SlashOption(description="Content", required=True)):
    await interaction.response.defer()
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Confirm Global Announcement", description=f"Send to ALL {len(bot.guilds)} servers?", color=0xFEE75C)
    await interaction.followup.send(embed=embed, view=view)
    await view.wait()
    if not view.value:
        return
    
    embed = Embed(title=f"📢 {title}", description=content, color=0xF1C40F)
    count = 0
    for guild in bot.guilds:
        guild_data = get_guild(guild.id)
        channel_id = guild_data["announcement_channel"]
        if channel_id:
            channel = bot.get_channel(channel_id)
            if channel:
                try:
                    await channel.send(embed=embed)
                    count += 1
                    continue
                except:
                    pass
        try:
            await guild.system_channel.send(embed=embed)
            count += 1
        except:
            pass
    
    embed = Embed(title="✅ Global Announcement Complete", description=f"Sent to {count} servers", color=0x57F287)
    await interaction.channel.send(embed=embed)

@bot.slash_command(name="global_dm", description="✉️ DM ALL users in ALL servers (GM only)")
@commands.is_owner()
async def global_dm(interaction: Interaction, message: str = SlashOption(description="Message to send", required=True)):
    await interaction.response.defer()
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Confirm Global DM", description=f"Send DM to ALL users in ALL {len(bot.guilds)} servers?", color=0xFEE75C)
    await interaction.followup.send(embed=embed, view=view)
    await view.wait()
    if not view.value:
        return
    
    users = set()
    for guild in bot.guilds:
        for member in guild.members:
            if not member.bot:
                users.add(member.id)
    
    embed = Embed(title="📢 Global Message", description=message, color=0x5865F2)
    sent = 0
    failed = 0
    for user_id in users:
        try:
            user = await bot.fetch_user(user_id)
            await user.send(embed=embed)
            sent += 1
            await asyncio.sleep(0.2)
        except:
            failed += 1
    
    embed = Embed(title="✅ Global DM Complete", description=f"Sent to {sent} users\nFailed: {failed}", color=0x57F287)
    await interaction.channel.send(embed=embed)

# ----- SETUP -----
@bot.slash_command(name="setup", description="⚙️ Setup bot channels")
@commands.has_permissions(administrator=True)
async def setup(interaction: Interaction, type: str = SlashOption(description="Type", choices={"welcome": "welcome", "mod_log": "mod_log", "level": "level", "announcement": "announcement"}, required=True), channel: nextcord.TextChannel = SlashOption(description="Channel", required=True)):
    update_guild(interaction.guild_id, **{f"{type}_channel": channel.id})
    embed = Embed(title="✅ Setup Complete", description=f"{type.capitalize()} channel set to {channel.mention}", color=0x57F287)
    await interaction.response.send_message(embed=embed)

# ===== FLASK KEEP-ALIVE =====
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Bot is online! 🇷🇴"

@app.route('/health')
def health():
    return jsonify({"status": "online", "timestamp": datetime.now().isoformat()})

def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

# ===== ERROR HANDLER =====
@bot.event
async def on_application_command_error(interaction: Interaction, error):
    if isinstance(error, commands.MissingPermissions):
        await interaction.response.send_message(embed=Embed(title="❌ Missing Permissions", description="You don't have permission!", color=0xED4245), ephemeral=True)
    else:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description=str(error), color=0xED4245), ephemeral=True)

# ===== MAIN =====
if __name__ == "__main__":
    thread = Thread(target=run_web, daemon=True)
    thread.start()
    bot.run(TOKEN)
