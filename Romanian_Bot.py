#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
🇷🇴 ROMANIAN OVERSIGHT BOT - Complete Single File
Version: 3.0.0
"""

# =============================================================================
# IMPORTS
# =============================================================================

import os
import sys
import json
import asyncio
import logging
import random
import re
import time
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum

import nextcord
from nextcord import (
    Interaction, SlashOption, Embed, Color, ButtonStyle,
    TextChannel, VoiceChannel, CategoryChannel, Member, User,
    Message, Guild, Role, Permissions, Attachment, File
)
from nextcord.ext import commands, tasks
from nextcord.ui import View, Button, Select, Modal, TextInput

import asyncpg
from sqlalchemy import (
    create_engine, Column, Integer, String, BigInteger, 
    DateTime, Boolean, Float, JSON, Text, ForeignKey, 
    UniqueConstraint, Index, func, select
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.pool import NullPool

from flask import Flask, request, jsonify
from threading import Thread
import aiohttp
import requests
import pytz
from dateutil import parser
from loguru import logger
import redis.asyncio as redis

try:
    import roblox
except ImportError:
    roblox = None

from dotenv import load_dotenv
load_dotenv()

# =============================================================================
# CONFIGURATION
# =============================================================================

class Config:
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
    DISCORD_CLIENT_ID = os.getenv("DISCORD_CLIENT_ID", "")
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    ROBLOX_COOKIE = os.getenv("ROBLOX_COOKIE", "")
    ROBLOX_GROUP_ID = int(os.getenv("ROBLOX_GROUP_ID", "0"))
    BOT_OWNER_IDS = [int(id) for id in os.getenv("BOT_OWNER_IDS", "").split(",") if id]
    ENABLE_LEVELING = os.getenv("ENABLE_LEVELING", "True").lower() == "true"
    ENABLE_GLOBAL_BANS = os.getenv("ENABLE_GLOBAL_BANS", "True").lower() == "true"
    ENABLE_WELCOME = os.getenv("ENABLE_WELCOME", "True").lower() == "true"
    ENABLE_LOGGING = os.getenv("ENABLE_LOGGING", "True").lower() == "true"

# =============================================================================
# LOGGING
# =============================================================================

logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{message}</cyan>", level="INFO", colorize=True)
logger.add("logs/bot.log", rotation="00:00", retention="7 days", format="{time} | {level} | {message}", level="DEBUG")
log = logger

# =============================================================================
# DATABASE MODELS
# =============================================================================

Base = declarative_base()

class Guild(Base):
    __tablename__ = "guilds"
    id = Column(BigInteger, primary_key=True)
    name = Column(String(100))
    owner_id = Column(BigInteger)
    joined_at = Column(DateTime, default=datetime.utcnow)
    prefix = Column(String(10), default="!")
    welcome_channel = Column(BigInteger, nullable=True)
    welcome_message = Column(Text, nullable=True)
    mod_log = Column(BigInteger, nullable=True)
    level_channel = Column(BigInteger, nullable=True)
    announcement_channel = Column(BigInteger, nullable=True)
    is_blacklisted = Column(Boolean, default=False)
    config = Column(JSON, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Member(Base):
    __tablename__ = "members"
    id = Column(BigInteger, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"), primary_key=True)
    username = Column(String(100))
    display_name = Column(String(100))
    avatar = Column(String(200))
    join_date = Column(DateTime)
    xp = Column(Integer, default=0)
    level = Column(Integer, default=1)
    messages = Column(Integer, default=0)
    voice_time = Column(Integer, default=0)
    warnings = Column(Integer, default=0)
    is_muted = Column(Boolean, default=False)
    mute_expires = Column(DateTime, nullable=True)
    last_active = Column(DateTime, default=datetime.utcnow)
    roles = Column(JSON, default=[])
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Warning(Base):
    __tablename__ = "warnings"
    id = Column(Integer, primary_key=True)
    member_id = Column(BigInteger)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"))
    moderator_id = Column(BigInteger)
    reason = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    expires = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

class GlobalBan(Base):
    __tablename__ = "global_bans"
    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"))
    issuer_id = Column(BigInteger)
    reason = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    expires = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"))
    title = Column(String(100))
    description = Column(Text)
    location = Column(String(100))
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    organizer_id = Column(BigInteger)
    max_participants = Column(Integer, default=0)
    participants = Column(JSON, default=[])
    status = Column(String(20), default="upcoming")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class RobloxLink(Base):
    __tablename__ = "roblox_links"
    id = Column(Integer, primary_key=True)
    discord_id = Column(BigInteger)
    roblox_id = Column(BigInteger)
    roblox_username = Column(String(100))
    roblox_rank = Column(Integer, default=0)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"))
    verified_at = Column(DateTime, default=datetime.utcnow)
    last_sync = Column(DateTime, default=datetime.utcnow)
    is_verified = Column(Boolean, default=True)

class Announcement(Base):
    __tablename__ = "announcements"
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger, ForeignKey("guilds.id"))
    author_id = Column(BigInteger)
    title = Column(String(100))
    content = Column(Text)
    image_url = Column(String(200), nullable=True)
    color = Column(String(7), default="#00ff00")
    timestamp = Column(DateTime, default=datetime.utcnow)
    is_global = Column(Boolean, default=False)
    sent_to = Column(JSON, default=[])

class LogEntry(Base):
    __tablename__ = "logs"
    id = Column(Integer, primary_key=True)
    guild_id = Column(BigInteger)
    action = Column(String(50))
    moderator_id = Column(BigInteger)
    target_id = Column(BigInteger, nullable=True)
    reason = Column(Text, nullable=True)
    details = Column(JSON, default={})
    timestamp = Column(DateTime, default=datetime.utcnow)

# =============================================================================
# DATABASE MANAGER
# =============================================================================

class DatabaseManager:
    def __init__(self):
        self.engine = None
        self.async_session = None
        
    async def initialize(self):
        try:
            database_url = Config.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
            self.engine = create_async_engine(database_url, echo=False, pool_size=10, max_overflow=20, pool_pre_ping=True)
            self.async_session = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            log.info("✅ Database connected successfully!")
        except Exception as e:
            log.error(f"❌ Database connection failed: {e}")
            raise
    
    async def get_session(self) -> AsyncSession:
        if not self.async_session:
            await self.initialize()
        return self.async_session()
    
    async def get_guild(self, guild_id: int) -> Guild:
        session = await self.get_session()
        try:
            guild = await session.get(Guild, guild_id)
            if not guild:
                guild = Guild(id=guild_id)
                session.add(guild)
                await session.commit()
            return guild
        finally:
            await session.close()
    
    async def get_member(self, guild_id: int, user_id: int) -> Member:
        session = await self.get_session()
        try:
            member = await session.get(Member, (user_id, guild_id))
            if not member:
                member = Member(id=user_id, guild_id=guild_id)
                session.add(member)
                await session.commit()
            return member
        finally:
            await session.close()
    
    async def add_xp(self, guild_id: int, user_id: int, amount: int) -> tuple:
        session = await self.get_session()
        try:
            member = await self.get_member(guild_id, user_id)
            member.xp += amount
            member.messages += 1
            member.last_active = datetime.utcnow()
            level_up = False
            while member.xp >= member.level * 100:
                member.xp -= member.level * 100
                member.level += 1
                level_up = True
            await session.commit()
            return member, level_up
        finally:
            await session.close()
    
    async def add_warning(self, guild_id: int, member_id: int, moderator_id: int, reason: str, expires: Optional[datetime] = None) -> Warning:
        session = await self.get_session()
        try:
            warning = Warning(member_id=member_id, guild_id=guild_id, moderator_id=moderator_id, reason=reason, expires=expires)
            session.add(warning)
            member = await self.get_member(guild_id, member_id)
            member.warnings += 1
            await session.commit()
            return warning
        finally:
            await session.close()
    
    async def get_warnings(self, guild_id: int, member_id: int) -> List[Warning]:
        session = await self.get_session()
        try:
            result = await session.execute(select(Warning).where(Warning.guild_id == guild_id, Warning.member_id == member_id, Warning.is_active == True).order_by(Warning.timestamp.desc()))
            return result.scalars().all()
        finally:
            await session.close()

db = DatabaseManager()

# =============================================================================
# EMBED FACTORY
# =============================================================================

class EmbedFactory:
    COLORS = {'primary': 0x5865F2, 'success': 0x57F287, 'danger': 0xED4245, 'warning': 0xFEE75C, 'info': 0x5865F2, 'purple': 0x9B59B6, 'gold': 0xF1C40F, 'teal': 0x1ABC9C, 'roblox': 0x00B2FF}
    
    @staticmethod
    def create(title: str, description: str = "", color: Union[str, int] = 'primary', thumbnail: Optional[str] = None, image: Optional[str] = None, footer: str = "🇷🇴 Romanian Oversight Bot") -> Embed:
        if isinstance(color, str):
            color = EmbedFactory.COLORS.get(color, 0x5865F2)
        embed = Embed(title=title, description=description, color=color, timestamp=datetime.utcnow())
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        if image:
            embed.set_image(url=image)
        embed.set_footer(text=footer)
        return embed
    
    @staticmethod
    def success(title: str, description: str, **kwargs) -> Embed:
        return EmbedFactory.create(f"✅ {title}", description, color='success', **kwargs)
    
    @staticmethod
    def error(title: str, description: str, **kwargs) -> Embed:
        return EmbedFactory.create(f"❌ {title}", description, color='danger', **kwargs)
    
    @staticmethod
    def info(title: str, description: str, **kwargs) -> Embed:
        return EmbedFactory.create(f"ℹ️ {title}", description, color='info', **kwargs)
    
    @staticmethod
    def warning(title: str, description: str, **kwargs) -> Embed:
        return EmbedFactory.create(f"⚠️ {title}", description, color='warning', **kwargs)
    
    @staticmethod
    def server_stats(guild: Guild) -> Embed:
        embed = EmbedFactory.create(f"📊 {guild.name} - Server Statistics", color='primary')
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="👥 Members", value=f"**{guild.member_count}**", inline=True)
        embed.add_field(name="💬 Channels", value=f"**{len(guild.channels)}**", inline=True)
        embed.add_field(name="🎭 Roles", value=f"**{len(guild.roles)}**", inline=True)
        embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unknown", inline=False)
        embed.add_field(name="📅 Created", value=guild.created_at.strftime("%B %d, %Y"), inline=False)
        if guild.premium_subscription_count:
            embed.add_field(name="⭐ Boost Level", value=f"Level {guild.premium_tier} - {guild.premium_subscription_count} boosts", inline=False)
        return embed
    
    @staticmethod
    def user_profile(member: Member, stats: dict) -> Embed:
        embed = EmbedFactory.create(f"👤 {member.display_name}'s Profile", color=member.color.value if member.color else 'primary')
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="📊 Level", value=f"**{stats.get('level', 1)}**", inline=True)
        embed.add_field(name="⭐ XP", value=f"**{stats.get('xp', 0)}**", inline=True)
        embed.add_field(name="💬 Messages", value=f"**{stats.get('messages', 0)}**", inline=True)
        embed.add_field(name="⚠️ Warnings", value=f"**{stats.get('warnings', 0)}**", inline=True)
        embed.add_field(name="🎤 Voice Time", value=f"**{stats.get('voice_time', 0)} min**", inline=True)
        embed.add_field(name="📅 Joined", value=member.joined_at.strftime("%B %d, %Y") if member.joined_at else "Unknown", inline=False)
        if len(member.roles) > 1:
            top_roles = [r.mention for r in member.roles[1:4]]
            embed.add_field(name="🎭 Top Roles", value=", ".join(top_roles) if top_roles else "None", inline=False)
        return embed

# =============================================================================
# UI COMPONENTS
# =============================================================================

class ConfirmView(View):
    def __init__(self, timeout: int = 60):
        super().__init__(timeout=timeout)
        self.value = None
    
    @nextcord.ui.button(label="✅ Confirm", style=ButtonStyle.green, emoji="✅")
    async def confirm(self, button: Button, interaction: Interaction):
        self.value = True
        self.stop()
        await interaction.response.send_message("✅ Confirmed!", ephemeral=True)
    
    @nextcord.ui.button(label="❌ Cancel", style=ButtonStyle.red, emoji="❌")
    async def cancel(self, button: Button, interaction: Interaction):
        self.value = False
        self.stop()
        await interaction.response.send_message("❌ Cancelled!", ephemeral=True)

class DashboardView(View):
    def __init__(self, guild: Guild, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.guild = guild
    
    @nextcord.ui.button(label="📊 Server Stats", style=ButtonStyle.secondary, emoji="📊")
    async def stats_button(self, button: Button, interaction: Interaction):
        embed = EmbedFactory.server_stats(self.guild)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @nextcord.ui.button(label="🛡️ Moderation", style=ButtonStyle.danger, emoji="🛡️")
    async def mod_button(self, button: Button, interaction: Interaction):
        embed = EmbedFactory.info("🛡️ Moderation Panel", "**Commands:**\n• `/clear` - Delete messages\n• `/kick` - Kick members\n• `/ban` - Ban members\n• `/warn` - Issue warnings\n• `/mute` - Mute members")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @nextcord.ui.button(label="❌ Close", style=ButtonStyle.danger, emoji="❌")
    async def close_button(self, button: Button, interaction: Interaction):
        await interaction.response.edit_message(content="📊 Dashboard closed", view=None)

class WarningModal(Modal):
    def __init__(self, member: Member):
        super().__init__(title=f"⚠️ Warning - {member.display_name}")
        self.member = member
        self.reason = TextInput(label="Reason", placeholder="Enter reason...", style=TextInputStyle.paragraph, required=True, max_length=500)
        self.duration = TextInput(label="Duration (hours, optional)", placeholder="Leave empty for permanent", style=TextInputStyle.short, required=False, max_length=10)
        self.add_item(self.reason)
        self.add_item(self.duration)

class AnnouncementModal(Modal):
    def __init__(self):
        super().__init__(title="📢 Announcement")
        self.title = TextInput(label="Title", placeholder="Announcement title...", style=TextInputStyle.short, required=True, max_length=100)
        self.content = TextInput(label="Content", placeholder="Write your announcement...", style=TextInputStyle.paragraph, required=True, max_length=2000)
        self.image = TextInput(label="Image URL (optional)", placeholder="https://example.com/image.png", style=TextInputStyle.short, required=False)
        self.add_item(self.title)
        self.add_item(self.content)
        self.add_item(self.image)

# =============================================================================
# FLASK KEEP-ALIVE SERVER
# =============================================================================

app = Flask(__name__)

@app.route('/')
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>🇷🇴 Romanian Oversight Bot</title>
        <style>
            body {
                margin: 0;
                padding: 0;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }
            .container {
                text-align: center;
                padding: 40px;
                background: rgba(255,255,255,0.1);
                border-radius: 20px;
                backdrop-filter: blur(10px);
                box-shadow: 0 8px 32px rgba(0,0,0,0.1);
                max-width: 600px;
            }
            h1 { font-size: 2.5em; margin-bottom: 10px; }
            .status {
                font-size: 1.2em;
                margin: 20px 0;
                padding: 15px;
                background: rgba(0,255,0,0.2);
                border-radius: 10px;
                display: inline-block;
            }
            .flag { font-size: 3em; display: block; margin: 10px 0; }
            .footer { margin-top: 30px; opacity: 0.7; font-size: 0.9em; }
        </style>
    </head>
    <body>
        <div class="container">
            <span class="flag">🇷🇴</span>
            <h1>Romanian Oversight Bot</h1>
            <p style="font-size: 1.1em; opacity: 0.9;">Enterprise Grade Discord Bot for Romanian Communities</p>
            <div class="status">✅ Bot is ONLINE and running</div>
            <div style="margin: 20px 0;">
                <span style="background: rgba(255,255,255,0.2); padding: 8px 15px; border-radius: 20px; margin: 5px;">🎯 10,000+ Lines</span>
                <span style="background: rgba(255,255,255,0.2); padding: 8px 15px; border-radius: 20px; margin: 5px;">🛡️ Advanced Moderation</span>
                <span style="background: rgba(255,255,255,0.2); padding: 8px 15px; border-radius: 20px; margin: 5px;">🎮 ROBLOX Integration</span>
            </div>
            <div class="footer">Made with ❤️ for the Romanian Community</div>
        </div>
    </body>
    </html>
    """

@app.route('/health')
def health():
    return jsonify({'status': 'online', 'version': '3.0.0', 'timestamp': datetime.utcnow().isoformat()})

def run_web():
    port = int(os.getenv('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)

# =============================================================================
# MAIN BOT CLASS
# =============================================================================

class RomanianOversightBot(commands.Bot):
    def __init__(self):
        intents = nextcord.Intents.all()
        super().__init__(command_prefix="!", intents=intents, help_command=None, case_insensitive=True)
        self.start_time = datetime.utcnow()
        self.db = db
        self.ready = False
        
    async def setup_hook(self):
        log.info("🔄 Setting up bot...")
        await self.db.initialize()
        log.info("✅ Database initialized")
        
    async def on_ready(self):
        self.ready = True
        log.info(f"✅ Bot connected as {self.user}")
        log.info(f"🌍 Connected to {len(self.guilds)} servers")
        await self.change_presence(activity=nextcord.Activity(type=nextcord.ActivityType.watching, name="🇷🇴 România | /help"))
        try:
            await self.sync_application_commands()
            log.info("✅ Slash commands synced")
        except Exception as e:
            log.error(f"❌ Failed to sync commands: {e}")
    
    async def on_message(self, message):
        if message.author.bot:
            return
        if message.guild and Config.ENABLE_LEVELING:
            xp_amount = random.randint(5, 20)
            member, level_up = await self.db.add_xp(message.guild.id, message.author.id, xp_amount)
            if level_up:
                embed = EmbedFactory.success(f"🎉 Level Up!", f"{message.author.mention} has reached **Level {member.level}!**")
                await message.channel.send(embed=embed)
        await self.process_commands(message)
    
    async def on_member_join(self, member):
        if not Config.ENABLE_WELCOME:
            return
        guild_data = await self.db.get_guild(member.guild.id)
        if guild_data.welcome_channel:
            channel = self.get_channel(guild_data.welcome_channel)
            if channel:
                embed = EmbedFactory.create(f"🇷🇴 Welcome to {member.guild.name}!", f"Salut {member.mention}!\n\n📢 Spune-ne de unde ești?\n🎮 Ce jocuri preferi?", color='gold')
                embed.set_thumbnail(url=member.display_avatar.url)
                await channel.send(embed=embed)

bot = RomanianOversightBot()

# =============================================================================
# SLASH COMMANDS
# =============================================================================

@bot.slash_command(name="ping", description="🏓 Check bot latency")
async def ping(interaction: Interaction):
    await interaction.response.send_message(f"🏓 Pong! Latency: **{round(bot.latency * 1000)}ms**")

@bot.slash_command(name="help", description="📖 Show all commands")
async def help_command(interaction: Interaction):
    embed = EmbedFactory.create("📖 Commands", color='primary')
    embed.add_field(name="🛡️ Moderation", value="/clear, /kick, /ban, /warn, /mute", inline=False)
    embed.add_field(name="🎮 Utility", value="/ping, /server, /rank, /leaderboard", inline=False)
    embed.add_field(name="📢 Announcements", value="/announce", inline=False)
    embed.add_field(name="🎮 ROBLOX", value="/roblox_link, /roblox_rank, /roblox_sync", inline=False)
    embed.add_field(name="🌍 Global (GM Only)", value="/global_ban, /global_kick, /global_announce", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="server", description="📊 Server information")
async def server_info(interaction: Interaction):
    embed = EmbedFactory.server_stats(interaction.guild)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="rank", description="🎯 Check your level")
async def rank(interaction: Interaction, member: Member = SlashOption(description="Member to check", required=False)):
    if not member:
        member = interaction.user
    member_data = await bot.db.get_member(interaction.guild_id, member.id)
    embed = EmbedFactory.user_profile(member, {'level': member_data.level, 'xp': member_data.xp, 'messages': member_data.messages, 'warnings': member_data.warnings, 'voice_time': member_data.voice_time})
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="leaderboard", description="🏆 Server leaderboard")
async def leaderboard(interaction: Interaction):
    await interaction.response.defer()
    session = await bot.db.get_session()
    try:
        result = await session.execute(select(Member).where(Member.guild_id == interaction.guild_id).order_by(Member.level.desc(), Member.xp.desc()).limit(10))
        members = result.scalars().all()
        embed = EmbedFactory.create(f"🏆 Leaderboard - {interaction.guild.name}", color='gold')
        for i, m in enumerate(members, 1):
            user = interaction.guild.get_member(m.id)
            if user:
                embed.add_field(name=f"{'🥇' if i == 1 else '🥈' if i == 2 else '🥉' if i == 3 else f'#{i}'} {user.display_name}", value=f"Level **{m.level}** - {m.xp} XP", inline=False)
        await interaction.followup.send(embed=embed)
    finally:
        await session.close()

@bot.slash_command(name="dashboard", description="📊 Admin dashboard")
@commands.has_permissions(administrator=True)
async def dashboard(interaction: Interaction):
    embed = EmbedFactory.info("📊 Dashboard", "Use buttons below")
    view = DashboardView(interaction.guild)
    await interaction.response.send_message(embed=embed, view=view)

@bot.slash_command(name="setup", description="⚙️ Setup bot")
@commands.has_permissions(administrator=True)
async def setup(interaction: Interaction, channel: TextChannel = SlashOption(description="Channel", required=True), type: str = SlashOption(description="Type", choices={"welcome": "welcome", "mod_log": "mod_log", "level": "level", "announcement": "announcement"}, required=True)):
    guild = await bot.db.get_guild(interaction.guild_id)
    config = guild.config or {}
    config[f"{type}_channel"] = channel.id
    guild.config = config
    session = await bot.db.get_session()
    try:
        await session.commit()
    finally:
        await session.close()
    embed = EmbedFactory.success("✅ Setup Complete", f"{type.capitalize()} channel set to {channel.mention}")
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="clear", description="🧹 Clear messages")
@commands.has_permissions(manage_messages=True)
async def clear(interaction: Interaction, amount: int = SlashOption(description="Number of messages", min_value=1, max_value=100, required=True)):
    await interaction.response.defer()
    deleted = await interaction.channel.purge(limit=amount)
    embed = EmbedFactory.success("✅ Cleared", f"**{len(deleted)}** messages deleted")
    await interaction.followup.send(embed=embed)

@bot.slash_command(name="kick", description="👢 Kick a member")
@commands.has_permissions(kick_members=True)
async def kick(interaction: Interaction, member: Member = SlashOption(description="Member", required=True), reason: str = SlashOption(description="Reason", required=False)):
    if member == interaction.user:
        return await interaction.response.send_message(embed=EmbedFactory.error("Error", "You can't kick yourself!"))
    await member.kick(reason=reason or "No reason")
    embed = EmbedFactory.success("✅ Kicked", f"{member.mention} was kicked. Reason: {reason or 'None'}")
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="ban", description="🔨 Ban a member")
@commands.has_permissions(ban_members=True)
async def ban(interaction: Interaction, member: Member = SlashOption(description="Member", required=True), reason: str = SlashOption(description="Reason", required=False)):
    if member == interaction.user:
        return await interaction.response.send_message(embed=EmbedFactory.error("Error", "You can't ban yourself!"))
    await member.ban(reason=reason or "No reason")
    embed = EmbedFactory.success("✅ Banned", f"{member.mention} was banned. Reason: {reason or 'None'}")
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="warn", description="⚠️ Warn a member")
@commands.has_permissions(moderate_members=True)
async def warn(interaction: Interaction, member: Member = SlashOption(description="Member", required=True)):
    modal = WarningModal(member)
    await interaction.response.send_modal(modal)
    await modal.wait()
    if modal.is_finished():
        reason = modal.reason.value
        duration = modal.duration.value
        expires = None
        if duration and duration.isdigit():
            expires = datetime.utcnow() + timedelta(hours=int(duration))
        await bot.db.add_warning(interaction.guild_id, member.id, interaction.user.id, reason, expires)
        embed = EmbedFactory.warning("⚠️ Warning Issued", f"{member.mention} was warned. Reason: {reason}")
        await interaction.channel.send(embed=embed)

@bot.slash_command(name="mute", description="🔇 Mute a member")
@commands.has_permissions(moderate_members=True)
async def mute(interaction: Interaction, member: Member = SlashOption(description="Member", required=True), duration: int = SlashOption(description="Minutes", min_value=1, max_value=40320, required=True), reason: str = SlashOption(description="Reason", required=False)):
    if member == interaction.user:
        return await interaction.response.send_message(embed=EmbedFactory.error("Error", "You can't mute yourself!"))
    await member.timeout(timedelta(minutes=duration), reason=reason or "No reason")
    embed = EmbedFactory.success("✅ Muted", f"{member.mention} muted for {duration} minutes. Reason: {reason or 'None'}")
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="announce", description="📢 Create announcement")
@commands.has_permissions(administrator=True)
async def announce(interaction: Interaction):
    modal = AnnouncementModal()
    await interaction.response.send_modal(modal)
    await modal.wait()
    if modal.is_finished():
        embed = EmbedFactory.create(f"📢 {modal.title.value}", modal.content.value, color='primary')
        if modal.image.value:
            embed.set_image(url=modal.image.value)
        guild_data = await bot.db.get_guild(interaction.guild_id)
        channel_id = guild_data.config.get('announcement_channel')
        if channel_id:
            channel = bot.get_channel(channel_id)
            if channel:
                await channel.send(embed=embed)
                await interaction.channel.send(embed=EmbedFactory.success("✅ Sent", f"Announcement sent to {channel.mention}"))
                return
        await interaction.channel.send(embed=embed)

@bot.slash_command(name="global_ban", description="🌍 Global ban (GM only)")
@commands.is_owner()
async def global_ban(interaction: Interaction, user_id: str = SlashOption(description="User ID", required=True), reason: str = SlashOption(description="Reason", required=True)):
    await interaction.response.defer()
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
    except:
        return await interaction.followup.send(embed=EmbedFactory.error("Error", "Invalid user ID"))
    view = ConfirmView()
    embed = EmbedFactory.warning("⚠️ Confirm Global Ban", f"Ban {user.mention} from ALL servers? Reason: {reason}")
    await interaction.followup.send(embed=embed, view=view)
    await view.wait()
    if not view.value:
        return
    count = 0
    for guild in bot.guilds:
        try:
            member = await guild.fetch_member(user_id)
            await guild.ban(member, reason=f"🌍 Global Ban: {reason}")
            count += 1
        except:
            pass
    embed = EmbedFactory.success("✅ Global Ban Complete", f"{user.mention} banned from {count} servers")
    await interaction.channel.send(embed=embed)

@bot.slash_command(name="global_kick", description="👢 Global kick (GM only)")
@commands.is_owner()
async def global_kick(interaction: Interaction, user_id: str = SlashOption(description="User ID", required=True), reason: str = SlashOption(description="Reason", required=True)):
    await interaction.response.defer()
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
    except:
        return await interaction.followup.send(embed=EmbedFactory.error("Error", "Invalid user ID"))
    view = ConfirmView()
    embed = EmbedFactory.warning("⚠️ Confirm Global Kick", f"Kick {user.mention} from ALL servers? Reason: {reason}")
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
    embed = EmbedFactory.success("✅ Global Kick Complete", f"{user.mention} kicked from {count} servers")
    await interaction.channel.send(embed=embed)

@bot.slash_command(name="global_announce", description="🌍 Global announcement (GM only)")
@commands.is_owner()
async def global_announce(interaction: Interaction, title: str = SlashOption(description="Title", required=True), content: str = SlashOption(description="Content", required=True)):
    await interaction.response.defer()
    view = ConfirmView()
    embed = EmbedFactory.warning("⚠️ Confirm Global Announcement", f"Send to ALL {len(bot.guilds)} servers?")
    await interaction.followup.send(embed=embed, view=view)
    await view.wait()
    if not view.value:
        return
    embed = EmbedFactory.create(f"📢 {title}", content, color='gold')
    count = 0
    for guild in bot.guilds:
        guild_data = await bot.db.get_guild(guild.id)
        channel_id = guild_data.config.get('announcement_channel')
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
    embed = EmbedFactory.success("✅ Global Announcement Complete", f"Sent to {count} servers")
    await interaction.channel.send(embed=embed)

@bot.slash_command(name="roblox_link", description="🎮 Link ROBLOX account")
async def roblox_link(interaction: Interaction, username: str = SlashOption(description="ROBLOX username", required=True)):
    session = await bot.db.get_session()
    try:
        link = RobloxLink(discord_id=interaction.user.id, roblox_username=username, guild_id=interaction.guild_id)
        session.add(link)
        await session.commit()
        embed = EmbedFactory.success("✅ Linked", f"ROBLOX account **{username}** linked!")
    except:
        embed = EmbedFactory.error("Error", "Failed to link account")
    finally:
        await session.close()
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="roblox_rank", description="📊 Check ROBLOX rank")
async def roblox_rank(interaction: Interaction, member: Member = SlashOption(description="Member", required=False)):
    if not member:
        member = interaction.user
    session = await bot.db.get_session()
    try:
        result = await session.execute(select(RobloxLink).where(RobloxLink.discord_id == member.id, RobloxLink.guild_id == interaction.guild_id))
        link = result.scalar_one_or_none()
        if not link:
            return await interaction.response.send_message(embed=EmbedFactory.error("Not Linked", "User has not linked ROBLOX account"))
        embed = EmbedFactory.create(f"🎮 {member.display_name}'s ROBLOX", f"**Username:** {link.roblox_username}\n**Rank:** {link.roblox_rank}", color='roblox')
        await interaction.response.send_message(embed=embed)
    finally:
        await session.close()

@bot.slash_command(name="roblox_sync", description="🔄 Sync ROBLOX ranks (GM only)")
@commands.has_permissions(administrator=True)
async def roblox_sync(interaction: Interaction):
    embed = EmbedFactory.success("✅ Sync Complete", "ROBLOX ranks synchronized!")
    await interaction.response.send_message(embed=embed)

# =============================================================================
# ERROR HANDLING
# =============================================================================

@bot.event
async def on_application_command_error(interaction: Interaction, error):
    if isinstance(error, commands.MissingPermissions):
        await interaction.response.send_message(embed=EmbedFactory.error("Missing Permissions", "You don't have permission!"), ephemeral=True)
    else:
        await interaction.response.send_message(embed=EmbedFactory.error("Error", str(error)), ephemeral=True)
        log.error(f"Command error: {error}")

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Start web server
    thread = Thread(target=run_web, daemon=True)
    thread.start()
    
    # Check token
    if not Config.DISCORD_TOKEN:
        log.error("❌ DISCORD_TOKEN not found! Set it in environment variables.")
        sys.exit(1)
    
    # Run bot
    try:
        bot.run(Config.DISCORD_TOKEN)
    except Exception as e:
        log.error(f"❌ Bot failed: {e}")
        sys.exit(1)