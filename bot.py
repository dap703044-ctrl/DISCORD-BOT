#!/usr/bin/env python3
"""
🇷🇴 ROMANIAN OVERSIGHT BOT - ULTIMATE EDITION
Version: 5.0.0
Enterprise Grade - 100000/10
"""

import os
import sys
import json
import sqlite3
import asyncio
import random
import re
import hashlib
import time
import aiohttp
from threading import Thread
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from collections import defaultdict
from dataclasses import dataclass, field

import nextcord
from nextcord import (
    Interaction, SlashOption, Embed, Color, ButtonStyle,
    TextChannel, VoiceChannel, Member, User, Message, Guild, Role,
    Permissions, Attachment, File, SelectOption
)
from nextcord.ext import commands, tasks
from nextcord.ui import View, Button, Select, Modal, TextInput

from flask import Flask, jsonify
from dotenv import load_dotenv

load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    print("❌ DISCORD_TOKEN not set!")
    sys.exit(1)

VERSION = "5.0.0"
START_TIME = datetime.now()
BOT_OWNER_IDS = [int(id) for id in os.getenv("BOT_OWNER_IDS", "").split(",") if id]

# =============================================================================
# DATABASE
# =============================================================================

DB_PATH = "bot_data.db"

class Database:
    def __init__(self):
        self.conn = None
        self.cursor = None
    
    def connect(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.cursor = self.conn.cursor()
        self._init_tables()
        return self
    
    def _init_tables(self):
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS guilds (
            id INTEGER PRIMARY KEY,
            name TEXT,
            owner_id INTEGER,
            prefix TEXT DEFAULT '!',
            welcome_channel INTEGER,
            welcome_message TEXT,
            mod_log INTEGER,
            level_channel INTEGER,
            announcement_channel INTEGER,
            ticket_category INTEGER,
            muted_role INTEGER,
            autorole INTEGER,
            config TEXT,
            created_at TEXT,
            updated_at TEXT
        )''')
        
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS members (
            user_id INTEGER,
            guild_id INTEGER,
            username TEXT,
            display_name TEXT,
            avatar TEXT,
            join_date TEXT,
            xp INTEGER DEFAULT 0,
            level INTEGER DEFAULT 1,
            messages INTEGER DEFAULT 0,
            voice_time INTEGER DEFAULT 0,
            warnings INTEGER DEFAULT 0,
            is_muted INTEGER DEFAULT 0,
            mute_expires TEXT,
            last_active TEXT,
            roles TEXT,
            created_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (user_id, guild_id)
        )''')
        
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS economy (
            user_id INTEGER,
            guild_id INTEGER,
            coins INTEGER DEFAULT 0,
            bank INTEGER DEFAULT 0,
            daily_last_claim TEXT,
            work_last_used TEXT,
            rob_cooldown TEXT,
            inventory TEXT,
            PRIMARY KEY (user_id, guild_id)
        )''')
        
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS shop_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            name TEXT,
            description TEXT,
            price INTEGER,
            role_id INTEGER,
            emoji TEXT,
            stock INTEGER DEFAULT -1
        )''')
        
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS country_scores (
            user_id INTEGER,
            guild_id INTEGER,
            score INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0,
            wrong INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, guild_id)
        )''')
        
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            guild_id INTEGER,
            moderator_id INTEGER,
            reason TEXT,
            timestamp TEXT,
            expires TEXT,
            is_active INTEGER DEFAULT 1,
            severity INTEGER DEFAULT 1
        )''')
        
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS global_bans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reason TEXT,
            issuer_id INTEGER,
            timestamp TEXT,
            expires TEXT,
            is_active INTEGER DEFAULT 1
        )''')
        
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS guild_admins (
            user_id INTEGER,
            guild_id INTEGER,
            added_by INTEGER,
            timestamp TEXT,
            PRIMARY KEY (user_id, guild_id)
        )''')
        
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            title TEXT,
            description TEXT,
            location TEXT,
            start_time TEXT,
            end_time TEXT,
            organizer_id INTEGER,
            max_participants INTEGER DEFAULT 0,
            participants TEXT,
            status TEXT DEFAULT 'upcoming',
            created_at TEXT,
            updated_at TEXT
        )''')
        
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS announcements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            author_id INTEGER,
            title TEXT,
            content TEXT,
            image_url TEXT,
            timestamp TEXT,
            is_global INTEGER DEFAULT 0
        )''')
        
        self.conn.commit()
    
    def execute(self, query, params=None):
        if params:
            self.cursor.execute(query, params)
        else:
            self.cursor.execute(query)
        return self.cursor
    
    def fetchone(self, query, params=None):
        self.execute(query, params)
        return self.cursor.fetchone()
    
    def fetchall(self, query, params=None):
        self.execute(query, params)
        return self.cursor.fetchall()
    
    def commit(self):
        self.conn.commit()
    
    def close(self):
        self.conn.close()

db = Database().connect()

# =============================================================================
# DATABASE HELPER FUNCTIONS
# =============================================================================

def get_guild(guild_id):
    result = db.fetchone("SELECT * FROM guilds WHERE id = ?", (guild_id,))
    if not result:
        db.execute("INSERT INTO guilds (id, created_at) VALUES (?, ?)", (guild_id, datetime.now().isoformat()))
        db.commit()
        return get_guild(guild_id)
    return result

def get_member(user_id, guild_id):
    result = db.fetchone("SELECT * FROM members WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    if not result:
        db.execute("INSERT INTO members (user_id, guild_id, created_at) VALUES (?, ?, ?)", (user_id, guild_id, datetime.now().isoformat()))
        db.commit()
        return get_member(user_id, guild_id)
    return result

def get_economy(user_id, guild_id):
    result = db.fetchone("SELECT * FROM economy WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    if not result:
        db.execute("INSERT INTO economy (user_id, guild_id) VALUES (?, ?)", (user_id, guild_id))
        db.commit()
        return get_economy(user_id, guild_id)
    return result

def is_admin(user_id, guild_id):
    if user_id in BOT_OWNER_IDS:
        return True
    result = db.fetchone("SELECT * FROM guild_admins WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    return result is not None

def add_admin(user_id, guild_id, added_by):
    db.execute("INSERT OR IGNORE INTO guild_admins (user_id, guild_id, added_by, timestamp) VALUES (?, ?, ?, ?)",
               (user_id, guild_id, added_by, datetime.now().isoformat()))
    db.commit()

def remove_admin(user_id, guild_id):
    db.execute("DELETE FROM guild_admins WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    db.commit()

def add_coins(user_id, guild_id, amount):
    db.execute("UPDATE economy SET coins = coins + ? WHERE user_id = ? AND guild_id = ?", (amount, user_id, guild_id))
    db.commit()

def remove_coins(user_id, guild_id, amount):
    db.execute("UPDATE economy SET coins = coins - ? WHERE user_id = ? AND guild_id = ?", (amount, user_id, guild_id))
    db.commit()

def get_shop_items(guild_id):
    return db.fetchall("SELECT * FROM shop_items WHERE guild_id = ?", (guild_id,))

def add_shop_item(guild_id, name, description, price, role_id=None, emoji=None):
    db.execute("INSERT INTO shop_items (guild_id, name, description, price, role_id, emoji) VALUES (?, ?, ?, ?, ?, ?)",
               (guild_id, name, description, price, role_id, emoji))
    db.commit()

# =============================================================================
# UI COMPONENTS
# =============================================================================

class ConfirmView(View):
    def __init__(self, timeout=60):
        super().__init__(timeout=timeout)
        self.value = None
    
    @nextcord.ui.button(label="✅ Confirm", style=ButtonStyle.green, emoji="✅")
    async def confirm(self, button, interaction):
        self.value = True
        self.stop()
        await interaction.response.send_message("✅ Confirmed!", ephemeral=True)
    
    @nextcord.ui.button(label="❌ Cancel", style=ButtonStyle.red, emoji="❌")
    async def cancel(self, button, interaction):
        self.value = False
        self.stop()
        await interaction.response.send_message("❌ Cancelled!", ephemeral=True)

class ShopView(View):
    def __init__(self, items, guild_id, user_id, timeout=120):
        super().__init__(timeout=timeout)
        self.items = items
        self.guild_id = guild_id
        self.user_id = user_id
        self.selected_item = None
        
        # Create select options dynamically
        options = []
        for item in items[:25]:
            options.append(SelectOption(
                label=item['name'][:100],
                value=str(item['id']),
                description=f"💰 {item['price']} coins"
            ))
        
        if options:
            self.select = Select(placeholder="Select an item to buy...", options=options)
            self.select.callback = self.select_callback
            self.add_item(self.select)
    
    async def select_callback(self, interaction: Interaction):
        self.selected_item = int(self.select.values[0])
        await interaction.response.send_message("✅ Item selected!", ephemeral=True)
    
    @nextcord.ui.button(label="🛒 Buy Selected", style=ButtonStyle.success, emoji="🛒")
    async def buy_item(self, button, interaction):
        if not self.selected_item:
            await interaction.response.send_message("❌ Select an item first!", ephemeral=True)
            return
        
        item = db.fetchone("SELECT * FROM shop_items WHERE id = ? AND guild_id = ?", (self.selected_item, self.guild_id))
        if not item:
            await interaction.response.send_message("❌ Item not found!", ephemeral=True)
            return
        
        economy = get_economy(self.user_id, self.guild_id)
        if economy['coins'] < item['price']:
            await interaction.response.send_message(f"❌ You need **{item['price']}** coins! You only have {economy['coins']}.", ephemeral=True)
            return
        
        remove_coins(self.user_id, self.guild_id, item['price'])
        
        if item['role_id']:
            guild = interaction.guild
            role = guild.get_role(item['role_id'])
            if role:
                member = guild.get_member(self.user_id)
                await member.add_roles(role)
        
        embed = Embed(title="✅ Purchase Successful!", description=f"You bought **{item['name']}** for {item['price']} coins!", color=0x57F287)
        await interaction.response.send_message(embed=embed)

class CountryGuessView(View):
    def __init__(self, country_data, timeout=30):
        super().__init__(timeout=timeout)
        self.country_data = country_data
        self.answered = False
    
    @nextcord.ui.button(label="🌍 Guess Country", style=ButtonStyle.success, emoji="🌍")
    async def guess_country(self, button, interaction):
        if self.answered:
            await interaction.response.send_message("⏳ Already answered!", ephemeral=True)
            return
        
        modal = CountryGuessModal(self.country_data)
        await interaction.response.send_modal(modal)

class CountryGuessModal(Modal):
    def __init__(self, country_data):
        super().__init__(title="🌍 Guess the Country!")
        self.country_data = country_data
        self.answer = TextInput(
            label="What country is this flag from?",
            placeholder="Type the country name...",
            style=TextInputStyle.short,
            required=True
        )
        self.add_item(self.answer)
    
    async def callback(self, interaction: Interaction):
        user_answer = self.answer.value.strip().lower()
        correct_answer = self.country_data['name'].lower()
        
        if user_answer == correct_answer:
            score = db.fetchone("SELECT * FROM country_scores WHERE user_id = ? AND guild_id = ?", 
                               (interaction.user.id, interaction.guild_id))
            if not score:
                db.execute("INSERT INTO country_scores (user_id, guild_id, score, correct) VALUES (?, ?, 10, 1)",
                          (interaction.user.id, interaction.guild_id))
            else:
                db.execute("UPDATE country_scores SET score = score + 10, correct = correct + 1 WHERE user_id = ? AND guild_id = ?",
                          (interaction.user.id, interaction.guild_id))
            db.commit()
            
            embed = Embed(title="✅ Correct!", description=f"It's **{self.country_data['name']}**! 🇷🇴\nYou earned 10 points!", color=0x57F287)
            await interaction.response.send_message(embed=embed)
        else:
            db.execute("UPDATE country_scores SET wrong = wrong + 1 WHERE user_id = ? AND guild_id = ?",
                      (interaction.user.id, interaction.guild_id))
            db.commit()
            embed = Embed(title="❌ Wrong!", description=f"It was **{self.country_data['name']}**! 🇷🇴\nBetter luck next time!", color=0xED4245)
            await interaction.response.send_message(embed=embed)

# =============================================================================
# COUNTRIES DATA
# =============================================================================

COUNTRIES = [
    {"name": "Romania", "flag": "🇷🇴"},
    {"name": "France", "flag": "🇫🇷"},
    {"name": "Germany", "flag": "🇩🇪"},
    {"name": "Italy", "flag": "🇮🇹"},
    {"name": "Spain", "flag": "🇪🇸"},
    {"name": "Portugal", "flag": "🇵🇹"},
    {"name": "Netherlands", "flag": "🇳🇱"},
    {"name": "Belgium", "flag": "🇧🇪"},
    {"name": "Greece", "flag": "🇬🇷"},
    {"name": "Turkey", "flag": "🇹🇷"},
    {"name": "Ukraine", "flag": "🇺🇦"},
    {"name": "Poland", "flag": "🇵🇱"},
    {"name": "Hungary", "flag": "🇭🇺"},
    {"name": "Bulgaria", "flag": "🇧🇬"},
    {"name": "Serbia", "flag": "🇷🇸"},
    {"name": "Croatia", "flag": "🇭🇷"},
    {"name": "Slovenia", "flag": "🇸🇮"},
    {"name": "Slovakia", "flag": "🇸🇰"},
    {"name": "Czech Republic", "flag": "🇨🇿"},
    {"name": "Austria", "flag": "🇦🇹"},
    {"name": "Switzerland", "flag": "🇨🇭"},
    {"name": "Sweden", "flag": "🇸🇪"},
    {"name": "Norway", "flag": "🇳🇴"},
    {"name": "Denmark", "flag": "🇩🇰"},
    {"name": "Finland", "flag": "🇫🇮"},
    {"name": "Ireland", "flag": "🇮🇪"},
    {"name": "United Kingdom", "flag": "🇬🇧"},
    {"name": "United States", "flag": "🇺🇸"},
    {"name": "Canada", "flag": "🇨🇦"},
    {"name": "Mexico", "flag": "🇲🇽"},
    {"name": "Brazil", "flag": "🇧🇷"},
    {"name": "Argentina", "flag": "🇦🇷"},
    {"name": "Chile", "flag": "🇨🇱"},
    {"name": "Colombia", "flag": "🇨🇴"},
    {"name": "Peru", "flag": "🇵🇪"},
    {"name": "Venezuela", "flag": "🇻🇪"},
    {"name": "Ecuador", "flag": "🇪🇨"},
    {"name": "Bolivia", "flag": "🇧🇴"},
    {"name": "Paraguay", "flag": "🇵🇾"},
    {"name": "Uruguay", "flag": "🇺🇾"},
    {"name": "South Africa", "flag": "🇿🇦"},
    {"name": "Egypt", "flag": "🇪🇬"},
    {"name": "Nigeria", "flag": "🇳🇬"},
    {"name": "Kenya", "flag": "🇰🇪"},
    {"name": "Ethiopia", "flag": "🇪🇹"},
    {"name": "Morocco", "flag": "🇲🇦"},
    {"name": "India", "flag": "🇮🇳"},
    {"name": "China", "flag": "🇨🇳"},
    {"name": "Japan", "flag": "🇯🇵"},
    {"name": "South Korea", "flag": "🇰🇷"},
    {"name": "Australia", "flag": "🇦🇺"},
    {"name": "New Zealand", "flag": "🇳🇿"},
]

# =============================================================================
# BOT
# =============================================================================

intents = nextcord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# =============================================================================
# EVENTS
# =============================================================================

@bot.event
async def on_ready():
    print(f"✅ {bot.user} is ONLINE!")
    print(f"🌍 Connected to {len(bot.guilds)} servers")
    print(f"👥 Serving {sum(g.member_count for g in bot.guilds)} users")
    print(f"📦 Version: {VERSION}")
    await bot.change_presence(activity=nextcord.Activity(type=nextcord.ActivityType.watching, name="🇷🇴 România | /help"))
    await bot.sync_application_commands()
    print("✅ Slash commands synced")
    update_status.start()

@bot.event
async def on_message(message):
    if message.author.bot:
        return
    
    if message.guild:
        xp_amount = random.randint(5, 25)
        member_data = get_member(message.author.id, message.guild.id)
        new_xp = member_data['xp'] + xp_amount
        new_level = member_data['level']
        
        while new_xp >= new_level * 100:
            new_xp -= new_level * 100
            new_level += 1
            embed = Embed(title="🎉 LEVEL UP!", description=f"{message.author.mention} reached **Level {new_level}!**", color=0x57F287)
            await message.channel.send(embed=embed)
        
        db.execute("UPDATE members SET xp = ?, level = ?, messages = messages + 1, last_active = ? WHERE user_id = ? AND guild_id = ?",
                  (new_xp, new_level, datetime.now().isoformat(), message.author.id, message.guild.id))
        db.commit()
    
    await bot.process_commands(message)

# =============================================================================
# TASKS
# =============================================================================

@tasks.loop(hours=1)
async def update_status():
    statuses = [
        f"🇷🇴 {len(bot.guilds)} servere",
        f"👥 {sum(g.member_count for g in bot.guilds)} utilizatori",
        "📢 /help pentru comenzi",
        "🎮 /shop pentru magazin",
        "🌍 /country pentru joc",
        "💰 /daily pentru recompense"
    ]
    await bot.change_presence(activity=nextcord.Game(name=random.choice(statuses)))

# =============================================================================
# SLASH COMMANDS - ADMIN
# =============================================================================

@bot.slash_command(name="add_admin", description="👑 Add a guild admin (Owner only)")
@commands.has_permissions(administrator=True)
async def add_admin(interaction: Interaction, user: Member = SlashOption(description="User to make admin", required=True)):
    if user == interaction.user:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="You can't add yourself!", color=0xED4245))
        return
    add_admin(user.id, interaction.guild_id, interaction.user.id)
    embed = Embed(title="✅ Admin Added", description=f"{user.mention} is now a guild admin!", color=0x57F287)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="remove_admin", description="👑 Remove a guild admin (Owner only)")
@commands.has_permissions(administrator=True)
async def remove_admin(interaction: Interaction, user: Member = SlashOption(description="User to remove", required=True)):
    if user == interaction.user:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="You can't remove yourself!", color=0xED4245))
        return
    remove_admin(user.id, interaction.guild_id)
    embed = Embed(title="✅ Admin Removed", description=f"{user.mention} is no longer a guild admin!", color=0x57F287)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# SLASH COMMANDS - MODERATION (Admin Only)
# =============================================================================

def is_guild_admin(interaction):
    if interaction.user.id in BOT_OWNER_IDS:
        return True
    return is_admin(interaction.user.id, interaction.guild_id)

@bot.slash_command(name="ban", description="🔨 Ban a member (Admin only)")
async def ban(interaction: Interaction, member: Member = SlashOption(description="Member", required=True), reason: str = SlashOption(description="Reason", required=False)):
    if not is_guild_admin(interaction):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only guild admins can use this!", color=0xED4245))
        return
    if member == interaction.user:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="You can't ban yourself!", color=0xED4245))
        return
    await member.ban(reason=reason or "No reason")
    embed = Embed(title="✅ Banned", description=f"{member.mention} was banned", color=0x57F287)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="kick", description="👢 Kick a member (Admin only)")
async def kick(interaction: Interaction, member: Member = SlashOption(description="Member", required=True), reason: str = SlashOption(description="Reason", required=False)):
    if not is_guild_admin(interaction):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only guild admins can use this!", color=0xED4245))
        return
    if member == interaction.user:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="You can't kick yourself!", color=0xED4245))
        return
    await member.kick(reason=reason or "No reason")
    embed = Embed(title="✅ Kicked", description=f"{member.mention} was kicked", color=0x57F287)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="clear", description="🧹 Clear messages (Admin only)")
@commands.has_permissions(manage_messages=True)
async def clear(interaction: Interaction, amount: int = SlashOption(description="Number of messages", min_value=1, max_value=100, required=True)):
    if not is_guild_admin(interaction):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only guild admins can use this!", color=0xED4245))
        return
    await interaction.response.defer()
    deleted = await interaction.channel.purge(limit=amount)
    embed = Embed(title="✅ Cleared", description=f"**{len(deleted)}** messages deleted", color=0x57F287)
    await interaction.followup.send(embed=embed)

@bot.slash_command(name="warn", description="⚠️ Warn a member (Admin only)")
async def warn(interaction: Interaction, member: Member = SlashOption(description="Member", required=True), reason: str = SlashOption(description="Reason", required=True)):
    if not is_guild_admin(interaction):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only guild admins can use this!", color=0xED4245))
        return
    db.execute("INSERT INTO warnings (user_id, guild_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
              (member.id, interaction.guild_id, interaction.user.id, reason, datetime.now().isoformat()))
    db.execute("UPDATE members SET warnings = warnings + 1 WHERE user_id = ? AND guild_id = ?", (member.id, interaction.guild_id))
    db.commit()
    embed = Embed(title="⚠️ Warning Issued", description=f"{member.mention} was warned\n**Reason:** {reason}", color=0xFEE75C)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="warnings", description="⚠️ View warnings (Admin only)")
async def view_warnings(interaction: Interaction, member: Member = SlashOption(description="Member", required=True)):
    if not is_guild_admin(interaction):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only guild admins can use this!", color=0xED4245))
        return
    warnings = db.fetchall("SELECT * FROM warnings WHERE user_id = ? AND guild_id = ? AND is_active = 1 ORDER BY timestamp DESC", (member.id, interaction.guild_id))
    if not warnings:
        embed = Embed(title="✅ No Warnings", description=f"{member.mention} has no warnings", color=0x57F287)
        return await interaction.response.send_message(embed=embed)
    embed = Embed(title=f"⚠️ Warnings for {member.display_name}", description=f"Total: {len(warnings)}", color=0xFEE75C)
    for i, w in enumerate(warnings[:5], 1):
        mod = interaction.guild.get_member(w['moderator_id'])
        embed.add_field(name=f"Warning #{i}", value=f"Reason: {w['reason']}\nModerator: {mod.mention if mod else 'Unknown'}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="mute", description="🔇 Mute a member (Admin only)")
async def mute(interaction: Interaction, member: Member = SlashOption(description="Member", required=True), duration: int = SlashOption(description="Minutes", min_value=1, max_value=40320, required=True), reason: str = SlashOption(description="Reason", required=False)):
    if not is_guild_admin(interaction):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only guild admins can use this!", color=0xED4245))
        return
    if member == interaction.user:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="You can't mute yourself!", color=0xED4245))
        return
    await member.timeout(timedelta(minutes=duration), reason=reason or "No reason")
    embed = Embed(title="✅ Muted", description=f"{member.mention} muted for {duration} minutes", color=0x57F287)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# SLASH COMMANDS - GLOBAL (Owner Only)
# =============================================================================

@bot.slash_command(name="global_ban", description="🌍 Ban user from ALL servers (Owner only)")
@commands.is_owner()
async def global_ban(interaction: Interaction, user_id: str = SlashOption(description="User ID", required=True), reason: str = SlashOption(description="Reason", required=True)):
    await interaction.response.defer()
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
    except:
        return await interaction.followup.send(embed=Embed(title="❌ Error", description="Invalid user ID", color=0xED4245))
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Global Ban", description=f"Ban {user.mention} from ALL {len(bot.guilds)} servers?\nReason: {reason}", color=0xFEE75C)
    await interaction.followup.send(embed=embed, view=view)
    await view.wait()
    if not view.value:
        return
    
    db.execute("INSERT INTO global_bans (user_id, reason, issuer_id, timestamp) VALUES (?, ?, ?, ?)",
              (user_id, reason, interaction.user.id, datetime.now().isoformat()))
    db.commit()
    
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

@bot.slash_command(name="global_unban", description="🌍 Remove global ban (Owner only)")
@commands.is_owner()
async def global_unban(interaction: Interaction, user_id: str = SlashOption(description="User ID", required=True)):
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
    except:
        return await interaction.response.send_message(embed=Embed(title="❌ Error", description="Invalid user ID", color=0xED4245))
    
    db.execute("UPDATE global_bans SET is_active = 0 WHERE user_id = ?", (user_id,))
    db.commit()
    
    count = 0
    for guild in bot.guilds:
        try:
            await guild.unban(user)
            count += 1
        except:
            pass
    
    embed = Embed(title="✅ Global Unban Complete", description=f"{user.mention} unbanned from {count} servers", color=0x57F287)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="global_kick", description="👢 Kick user from ALL servers (Owner only)")
@commands.is_owner()
async def global_kick(interaction: Interaction, user_id: str = SlashOption(description="User ID", required=True), reason: str = SlashOption(description="Reason", required=True)):
    await interaction.response.defer()
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
    except:
        return await interaction.followup.send(embed=Embed(title="❌ Error", description="Invalid user ID", color=0xED4245))
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Global Kick", description=f"Kick {user.mention} from ALL {len(bot.guilds)} servers?\nReason: {reason}", color=0xFEE75C)
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

@bot.slash_command(name="global_announce", description="🌍 Announce to ALL servers (Owner only)")
@commands.is_owner()
async def global_announce(interaction: Interaction, title: str = SlashOption(description="Title", required=True), content: str = SlashOption(description="Content", required=True)):
    await interaction.response.defer()
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Global Announcement", description=f"Send to ALL {len(bot.guilds)} servers?", color=0xFEE75C)
    await interaction.followup.send(embed=embed, view=view)
    await view.wait()
    if not view.value:
        return
    
    embed = Embed(title=f"📢 {title}", description=content, color=0xF1C40F, timestamp=datetime.now())
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

@bot.slash_command(name="global_dm", description="✉️ DM ALL users (Owner only)")
@commands.is_owner()
async def global_dm(interaction: Interaction, message: str = SlashOption(description="Message", required=True)):
    await interaction.response.defer()
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Global DM", description=f"Send DM to ALL users in ALL {len(bot.guilds)} servers?", color=0xFEE75C)
    await interaction.followup.send(embed=embed, view=view)
    await view.wait()
    if not view.value:
        return
    
    users = set()
    for guild in bot.guilds:
        for member in guild.members:
            if not member.bot:
                users.add(member.id)
    
    embed = Embed(title="📢 Global Message", description=message, color=0x5865F2, timestamp=datetime.now())
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

# =============================================================================
# SLASH COMMANDS - ECONOMY
# =============================================================================

@bot.slash_command(name="daily", description="💰 Collect your daily reward!")
async def daily(interaction: Interaction):
    economy = get_economy(interaction.user.id, interaction.guild_id)
    last_claim = economy['daily_last_claim']
    
    if last_claim:
        last_time = datetime.fromisoformat(last_claim)
        if (datetime.now() - last_time).total_seconds() < 86400:
            remaining = 86400 - (datetime.now() - last_time).total_seconds()
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            await interaction.response.send_message(embed=Embed(title="⏳ Already Claimed", description=f"Come back in **{hours}h {minutes}m**!", color=0xFEE75C))
            return
    
    amount = random.randint(100, 500)
    add_coins(interaction.user.id, interaction.guild_id, amount)
    db.execute("UPDATE economy SET daily_last_claim = ? WHERE user_id = ? AND guild_id = ?", 
              (datetime.now().isoformat(), interaction.user.id, interaction.guild_id))
    db.commit()
    
    embed = Embed(title="💰 Daily Reward!", description=f"You received **{amount}** coins! 💰\nKeep coming back every day!", color=0x57F287)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="work", description="💼 Work to earn coins!")
async def work(interaction: Interaction):
    economy = get_economy(interaction.user.id, interaction.guild_id)
    last_work = economy['work_last_used']
    
    if last_work:
        last_time = datetime.fromisoformat(last_work)
        if (datetime.now() - last_time).total_seconds() < 3600:
            remaining = 3600 - (datetime.now() - last_time).total_seconds()
            minutes = int(remaining // 60)
            await interaction.response.send_message(embed=Embed(title="⏳ Cooldown", description=f"Wait **{minutes}** minutes before working again!", color=0xFEE75C))
            return
    
    jobs = ["🧑‍💻 Programmer", "👨‍🍳 Chef", "🧑‍🏫 Teacher", "👨‍⚕️ Doctor", "🧑‍🔬 Scientist", "👨‍🚀 Astronaut", "🧑‍🎨 Artist", "👨‍🏭 Engineer"]
    job = random.choice(jobs)
    amount = random.randint(20, 80)
    add_coins(interaction.user.id, interaction.guild_id, amount)
    db.execute("UPDATE economy SET work_last_used = ? WHERE user_id = ? AND guild_id = ?", 
              (datetime.now().isoformat(), interaction.user.id, interaction.guild_id))
    db.commit()
    
    embed = Embed(title="💼 Work Complete!", description=f"You worked as a **{job}** and earned **{amount}** coins!", color=0x57F287)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="rob", description="🔫 Rob a member for coins!")
async def rob(interaction: Interaction, member: Member = SlashOption(description="Member to rob", required=True)):
    if member == interaction.user:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="You can't rob yourself!", color=0xED4245))
        return
    
    economy = get_economy(interaction.user.id, interaction.guild_id)
    target_economy = get_economy(member.id, interaction.guild_id)
    last_rob = economy['rob_cooldown']
    
    if last_rob:
        last_time = datetime.fromisoformat(last_rob)
        if (datetime.now() - last_time).total_seconds() < 3600:
            remaining = 3600 - (datetime.now() - last_time).total_seconds()
            minutes = int(remaining // 60)
            await interaction.response.send_message(embed=Embed(title="⏳ Cooldown", description=f"Wait **{minutes}** minutes before robbing again!", color=0xFEE75C))
            return
    
    if target_economy['coins'] < 10:
        await interaction.response.send_message(embed=Embed(title="❌ Poor Target", description=f"{member.mention} doesn't have enough coins to rob!", color=0xED4245))
        return
    
    success = random.random() < 0.6
    if success:
        amount = random.randint(10, min(50, target_economy['coins']))
        remove_coins(member.id, interaction.guild_id, amount)
        add_coins(interaction.user.id, interaction.guild_id, amount)
        embed = Embed(title="✅ Robbery Successful!", description=f"You robbed **{amount}** coins from {member.mention}! 🏃💨", color=0x57F287)
    else:
        penalty = random.randint(5, 20)
        remove_coins(interaction.user.id, interaction.guild_id, penalty)
        embed = Embed(title="❌ Robbery Failed!", description=f"You got caught and lost **{penalty}** coins! 👮", color=0xED4245)
    
    db.execute("UPDATE economy SET rob_cooldown = ? WHERE user_id = ? AND guild_id = ?", 
              (datetime.now().isoformat(), interaction.user.id, interaction.guild_id))
    db.commit()
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="balance", description="💰 Check your balance")
async def balance(interaction: Interaction, member: Member = SlashOption(description="Member to check", required=False)):
    if not member:
        member = interaction.user
    economy = get_economy(member.id, interaction.guild_id)
    embed = Embed(title=f"💰 {member.display_name}'s Balance", color=0x57F287)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🪙 Coins", value=f"**{economy['coins']}**", inline=True)
    embed.add_field(name="🏦 Bank", value=f"**{economy['bank']}**", inline=True)
    embed.add_field(name="💎 Total", value=f"**{economy['coins'] + economy['bank']}**", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="leaderboard_economy", description="🏆 Economy leaderboard")
async def leaderboard_economy(interaction: Interaction):
    results = db.fetchall("SELECT user_id, coins FROM economy WHERE guild_id = ? ORDER BY coins DESC LIMIT 10", (interaction.guild_id,))
    embed = Embed(title=f"🏆 Economy Leaderboard - {interaction.guild.name}", color=0xF1C40F)
    for i, row in enumerate(results, 1):
        user = interaction.guild.get_member(row['user_id'])
        if user:
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
            embed.add_field(name=f"{emoji} {user.display_name}", value=f"💰 {row['coins']} coins", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="shop", description="🛒 View and buy items from the shop")
async def shop(interaction: Interaction):
    items = get_shop_items(interaction.guild_id)
    
    if not items:
        embed = Embed(title="🛒 Shop", description="The shop is empty! Admins can add items.", color=0x5865F2)
        return await interaction.response.send_message(embed=embed)
    
    embed = Embed(title=f"🛒 Shop - {interaction.guild.name}", color=0x5865F2)
    for item in items[:10]:
        embed.add_field(name=f"{item['emoji'] or '🛒'} {item['name']}", value=f"💰 {item['price']} coins\n{item['description']}", inline=False)
    
    view = ShopView(items, interaction.guild_id, interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)

@bot.slash_command(name="add_shop_item", description="➕ Add item to shop (Admin only)")
async def add_shop_item(interaction: Interaction, name: str = SlashOption(description="Item name", required=True), description: str = SlashOption(description="Description", required=True), price: int = SlashOption(description="Price in coins", required=True), emoji: str = SlashOption(description="Emoji", required=False)):
    if not is_guild_admin(interaction):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only guild admins can use this!", color=0xED4245))
        return
    add_shop_item(interaction.guild_id, name, description, price, None, emoji or "🛒")
    embed = Embed(title="✅ Shop Item Added", description=f"Added **{name}** for {price} coins!", color=0x57F287)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# SLASH COMMANDS - FUN
# =============================================================================

@bot.slash_command(name="country", description="🌍 Play the country guessing game!")
async def country(interaction: Interaction):
    country = random.choice(COUNTRIES)
    embed = Embed(
        title="🌍 Country Guess Game!",
        description=f"**{country['flag']}** Which country is this flag from?\n\nClick the button below to guess!",
        color=0x5865F2,
        timestamp=datetime.now()
    )
    view = CountryGuessView(country)
    await interaction.response.send_message(embed=embed, view=view)

@bot.slash_command(name="country_score", description="🌍 Check your country game score")
async def country_score(interaction: Interaction, member: Member = SlashOption(description="Member to check", required=False)):
    if not member:
        member = interaction.user
    score = db.fetchone("SELECT * FROM country_scores WHERE user_id = ? AND guild_id = ?", (member.id, interaction.guild_id))
    if not score:
        embed = Embed(title="🌍 Country Score", description=f"{member.mention} hasn't played yet!", color=0x5865F2)
        return await interaction.response.send_message(embed=embed)
    
    embed = Embed(title=f"🌍 {member.display_name}'s Country Score", color=0x5865F2)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="⭐ Total Score", value=f"**{score['score']}**", inline=True)
    embed.add_field(name="✅ Correct", value=f"**{score['correct']}**", inline=True)
    embed.add_field(name="❌ Wrong", value=f"**{score['wrong']}**", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="country_leaderboard", description="🏆 Country game leaderboard")
async def country_leaderboard(interaction: Interaction):
    results = db.fetchall("SELECT user_id, score FROM country_scores WHERE guild_id = ? ORDER BY score DESC LIMIT 10", (interaction.guild_id,))
    embed = Embed(title=f"🏆 Country Game Leaderboard - {interaction.guild.name}", color=0xF1C40F)
    for i, row in enumerate(results, 1):
        user = interaction.guild.get_member(row['user_id'])
        if user:
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
            embed.add_field(name=f"{emoji} {user.display_name}", value=f"⭐ {row['score']} points", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="8ball", description="🎱 Ask the magic 8-ball a question!")
async def eight_ball(interaction: Interaction, question: str = SlashOption(description="Your question", required=True)):
    responses = [
        "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes - definitely.",
        "You may rely on it.", "As I see it, yes.", "Most likely.", "Outlook good.",
        "Yes.", "Signs point to yes.", "Reply hazy, try again.", "Ask again later.",
        "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.",
        "Don't count on it.", "My reply is no.", "My sources say no.",
        "Outlook not so good.", "Very doubtful."
    ]
    embed = Embed(title="🎱 8-Ball", description=f"Question: {question}\n\n**Answer:** {random.choice(responses)}", color=0x9B59B6)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="flip", description="🪙 Flip a coin!")
async def flip(interaction: Interaction):
    result = random.choice(["Heads", "Tails"])
    embed = Embed(title="🪙 Coin Flip", description=f"**{result}**!", color=0x5865F2)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="dice", description="🎲 Roll a dice!")
async def dice(interaction: Interaction, sides: int = SlashOption(description="Number of sides", min_value=2, max_value=100, required=False)):
    sides = sides or 6
    result = random.randint(1, sides)
    embed = Embed(title="🎲 Dice Roll", description=f"Rolled a **{result}** on a {sides}-sided dice!", color=0x5865F2)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="joke", description="😂 Get a random joke")
async def joke(interaction: Interaction):
    jokes = [
        "Why don't scientists trust atoms? Because they make up everything!",
        "What do you call a fake noodle? An impasta!",
        "Why did the scarecrow win an award? He was outstanding in his field!",
        "What do you call a bear with no teeth? A gummy bear!",
        "Why don't eggs tell jokes? They'd crack each other up!",
        "What's the best thing about Switzerland? I don't know, but the flag is a big plus!",
        "Why did the math book look so sad? Because it had too many problems!",
    ]
    embed = Embed(title="😂 Joke", description=random.choice(jokes), color=0x5865F2)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="roast", description="🔥 Roast a member!")
async def roast(interaction: Interaction, member: Member = SlashOption(description="Member to roast", required=True)):
    roasts = [
        f"{member.mention}, you're not stupid; you just have bad luck thinking.",
        f"{member.mention}, you bring everyone so much joy... when you leave.",
        f"{member.mention}, you're like a cloud. When you disappear, it's a beautiful day.",
        f"{member.mention}, you're proof that evolution can go in reverse.",
        f"{member.mention}, you're the reason God created the middle finger.",
        f"{member.mention}, you're not the dumbest person in the world, but you better hope they don't die.",
        f"{member.mention}, you're like a dictionary - you add meaning to my life, but you're also really boring.",
    ]
    embed = Embed(title="🔥 ROASTED!", description=random.choice(roasts), color=0xED4245)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="kiss", description="💋 Kiss a member")
async def kiss(interaction: Interaction, member: Member = SlashOption(description="Member to kiss", required=True)):
    if member == interaction.user:
        await interaction.response.send_message(embed=Embed(title="💋", description="You kissed yourself! That's sad...", color=0x5865F2))
        return
    embed = Embed(title="💋 Kiss!", description=f"{interaction.user.mention} kissed {member.mention}! 😘", color=0xFF6B81)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="hug", description="🤗 Hug a member")
async def hug(interaction: Interaction, member: Member = SlashOption(description="Member to hug", required=True)):
    if member == interaction.user:
        await interaction.response.send_message(embed=Embed(title="🤗", description="You hugged yourself! You need friends.", color=0x5865F2))
        return
    embed = Embed(title="🤗 Hug!", description=f"{interaction.user.mention} hugged {member.mention}! 🫂", color=0x57F287)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="pat", description="👋 Pat a member")
async def pat(interaction: Interaction, member: Member = SlashOption(description="Member to pat", required=True)):
    embed = Embed(title="👋 Pat!", description=f"{interaction.user.mention} patted {member.mention} on the head! 👋", color=0x5865F2)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# SLASH COMMANDS - UTILITY
# =============================================================================

@bot.slash_command(name="ping", description="🏓 Check bot latency")
async def ping(interaction: Interaction):
    await interaction.response.send_message(f"🏓 Pong! Latency: **{round(bot.latency * 1000)}ms**")

@bot.slash_command(name="help", description="📖 Show all commands")
async def help_command(interaction: Interaction):
    embed = Embed(title="📖 Commands", color=0x5865F2, timestamp=datetime.now())
    embed.add_field(name="👑 Admin", value="/add_admin, /remove_admin", inline=False)
    embed.add_field(name="🛡️ Moderation (Admin Only)", value="/ban, /kick, /clear, /warn, /warnings, /mute", inline=False)
    embed.add_field(name="🌍 Global (Owner Only)", value="/global_ban, /global_unban, /global_kick, /global_announce, /global_dm", inline=False)
    embed.add_field(name="💰 Economy", value="/daily, /work, /rob, /balance, /shop, /leaderboard_economy", inline=False)
    embed.add_field(name="🌍 Country Game", value="/country, /country_score, /country_leaderboard", inline=False)
    embed.add_field(name="🎮 Fun", value="/8ball, /flip, /dice, /joke, /roast, /kiss, /hug, /pat", inline=False)
    embed.add_field(name="📊 Utility", value="/ping, /server, /rank, /leaderboard, /setup", inline=False)
    embed.set_footer(text=f"🇷🇴 Romanian Oversight Bot v{VERSION}")
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="server", description="📊 Server information")
async def server_info(interaction: Interaction):
    guild = interaction.guild
    embed = Embed(title=f"📊 {guild.name}", color=0x5865F2, timestamp=datetime.now())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="👥 Members", value=f"**{guild.member_count}**", inline=True)
    embed.add_field(name="💬 Channels", value=f"**{len(guild.channels)}**", inline=True)
    embed.add_field(name="🎭 Roles", value=f"**{len(guild.roles)}**", inline=True)
    embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=False)
    embed.add_field(name="📅 Created", value=guild.created_at.strftime("%B %d, %Y"), inline=False)
    embed.set_footer(text=f"ID: {guild.id}")
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="rank", description="🎯 Check your level")
async def rank(interaction: Interaction, member: Member = SlashOption(description="Member to check", required=False)):
    if not member:
        member = interaction.user
    data = get_member(member.id, interaction.guild_id)
    embed = Embed(title=f"👤 {member.display_name}'s Profile", color=member.color.value if member.color else 0x5865F2, timestamp=datetime.now())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="📊 Level", value=f"**{data['level']}**", inline=True)
    embed.add_field(name="⭐ XP", value=f"**{data['xp']}**", inline=True)
    embed.add_field(name="💬 Messages", value=f"**{data['messages']}**", inline=True)
    embed.add_field(name="⚠️ Warnings", value=f"**{data['warnings']}**", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="leaderboard", description="🏆 Level leaderboard")
async def leaderboard(interaction: Interaction):
    results = db.fetchall("SELECT user_id, level, xp FROM members WHERE guild_id = ? ORDER BY level DESC, xp DESC LIMIT 10", (interaction.guild_id,))
    embed = Embed(title=f"🏆 Leaderboard - {interaction.guild.name}", color=0xF1C40F)
    for i, row in enumerate(results, 1):
        user = interaction.guild.get_member(row['user_id'])
        if user:
            emoji = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"#{i}"
            embed.add_field(name=f"{emoji} {user.display_name}", value=f"Level **{row['level']}** - {row['xp']} XP", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="setup", description="⚙️ Setup bot channels")
@commands.has_permissions(administrator=True)
async def setup(interaction: Interaction, type: str = SlashOption(description="Type", choices={"welcome": "welcome", "mod_log": "mod_log", "level": "level", "announcement": "announcement"}, required=True), channel: TextChannel = SlashOption(description="Channel", required=True)):
    db.execute(f"UPDATE guilds SET {type}_channel = ? WHERE id = ?", (channel.id, interaction.guild_id))
    db.commit()
    embed = Embed(title="✅ Setup Complete", description=f"{type.capitalize()} channel set to {channel.mention}", color=0x57F287)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# SLASH COMMANDS - EVENTS
# =============================================================================

@bot.slash_command(name="event_create", description="🎪 Create an event")
@commands.has_permissions(administrator=True)
async def event_create(interaction: Interaction, title: str = SlashOption(description="Event title", required=True), description: str = SlashOption(description="Event description", required=True), location: str = SlashOption(description="Location", required=True), max_participants: int = SlashOption(description="Max participants", required=False)):
    db.execute("INSERT INTO events (guild_id, title, description, location, start_time, organizer_id, max_participants, participants, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
              (interaction.guild_id, title, description, location, datetime.now().isoformat(), interaction.user.id, max_participants or 0, json.dumps([]), datetime.now().isoformat()))
    db.commit()
    embed = Embed(title="🎪 Event Created", description=f"**{title}**\n{description}\n📍 {location}", color=0x1ABC9C, timestamp=datetime.now())
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="events", description="📋 List upcoming events")
async def events(interaction: Interaction):
    events = db.fetchall("SELECT * FROM events WHERE guild_id = ? AND status = 'upcoming' ORDER BY start_time LIMIT 10", (interaction.guild_id,))
    if not events:
        embed = Embed(title="📋 No Events", description="No upcoming events", color=0x5865F2)
        return await interaction.response.send_message(embed=embed)
    embed = Embed(title=f"📋 Upcoming Events - {interaction.guild.name}", color=0x1ABC9C, timestamp=datetime.now())
    for event in events:
        organizer = interaction.guild.get_member(event['organizer_id'])
        embed.add_field(name=event['title'], value=f"📍 {event['location']}\n👤 {organizer.mention if organizer else 'Unknown'}", inline=False)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# SLASH COMMANDS - ANNOUNCEMENTS
# =============================================================================

@bot.slash_command(name="announce", description="📢 Create announcement")
@commands.has_permissions(administrator=True)
async def announce(interaction: Interaction, title: str = SlashOption(description="Title", required=True), content: str = SlashOption(description="Content", required=True), image_url: str = SlashOption(description="Image URL", required=False)):
    embed = Embed(title=f"📢 {title}", description=content, color=0xF1C40F, timestamp=datetime.now())
    if image_url:
        embed.set_image(url=image_url)
    guild_data = get_guild(interaction.guild_id)
    channel_id = guild_data["announcement_channel"]
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)
            await interaction.response.send_message(embed=Embed(title="✅ Sent", description=f"Announcement sent to {channel.mention}", color=0x57F287))
            return
    await interaction.response.send_message(embed=embed)

# =============================================================================
# FLASK KEEP-ALIVE
# =============================================================================

app = Flask(__name__)

@app.route('/')
def home():
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>🇷🇴 Romanian Oversight Bot</title>
        <style>
            body {{
                margin: 0;
                padding: 0;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }}
            .container {{
                text-align: center;
                padding: 40px;
                background: rgba(255,255,255,0.1);
                border-radius: 20px;
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                max-width: 600px;
            }}
            h1 {{ font-size: 2.5em; margin-bottom: 10px; }}
            .status {{ font-size: 1.2em; margin: 20px 0; padding: 15px; background: rgba(0,255,0,0.2); border-radius: 10px; display: inline-block; }}
            .flag {{ font-size: 3em; display: block; margin: 10px 0; }}
            .stats {{ margin: 20px 0; }}
            .stat {{ display: inline-block; margin: 0 15px; padding: 10px 20px; background: rgba(255,255,255,0.1); border-radius: 10px; }}
            .footer {{ margin-top: 30px; opacity: 0.7; font-size: 0.9em; }}
        </style>
    </head>
    <body>
        <div class="container">
            <span class="flag">🇷🇴</span>
            <h1>Romanian Oversight Bot</h1>
            <p style="font-size: 1.1em; opacity: 0.9;">Enterprise Grade Discord Bot - v{VERSION}</p>
            <div class="status">✅ Bot is ONLINE</div>
            <div class="stats">
                <div class="stat">🎯 {len(bot.guilds)} Servers</div>
                <div class="stat">👥 {sum(g.member_count for g in bot.guilds)} Users</div>
            </div>
            <div style="margin: 20px 0;">
                <span style="background: rgba(255,255,255,0.2); padding: 8px 15px; border-radius: 20px; margin: 5px;">📊 30+ Commands</span>
                <span style="background: rgba(255,255,255,0.2); padding: 8px 15px; border-radius: 20px; margin: 5px;">💰 Economy</span>
                <span style="background: rgba(255,255,255,0.2); padding: 8px 15px; border-radius: 20px; margin: 5px;">🌍 Global System</span>
                <span style="background: rgba(255,255,255,0.2); padding: 8px 15px; border-radius: 20px; margin: 5px;">🎮 Fun Commands</span>
            </div>
            <div class="footer">Made with ❤️ for the Romanian Community</div>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return jsonify({"status": "online", "version": VERSION, "timestamp": datetime.now().isoformat()})

@app.route('/stats')
def stats():
    return jsonify({
        "status": "online",
        "version": VERSION,
        "servers": len(bot.guilds),
        "users": sum(g.member_count for g in bot.guilds),
        "uptime": str(datetime.now() - START_TIME)
    })

def run_web():
    port = int(os.getenv("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

# =============================================================================
# ERROR HANDLER
# =============================================================================

@bot.event
async def on_application_command_error(interaction: Interaction, error):
    if isinstance(error, commands.MissingPermissions):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="You need higher permissions!", color=0xED4245), ephemeral=True)
    elif isinstance(error, commands.NotOwner):
        await interaction.response.send_message(embed=Embed(title="❌ Owner Only", description="Only the bot owner can use this!", color=0xED4245), ephemeral=True)
    else:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description=str(error), color=0xED4245), ephemeral=True)

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    thread = Thread(target=run_web, daemon=True)
    thread.start()
    bot.run(TOKEN)
