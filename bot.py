#!/usr/bin/env python3
"""
🇷🇴 ROMANIAN OVERSIGHT BOT - PROFESSIONAL ENTERPRISE EDITION
Version: 9.0.0
For 3000+ Member Servers
Features:
- Advanced Ticket System with Panels, Transcripts, Claims
- Group Management System (Top Level)
- Group Administrator System (Second Level)
- Global Ranking System (Manual Sync)
- Server Role Sync System
- Full Economy System
- 100+ Professional Commands
- Auto-Recovery & Backup
- Beautiful UI/UX
- Audit Logging
- Welcome System
- Leveling System
- ALPHA SYSTEM (TommyTactical - Ultimate Power)
- Customizable Ticket Panels
- Official "Romanian Group Management" Branding
- And Much More!
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
import signal
import traceback
import shutil
from threading import Thread
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union
from collections import defaultdict
from dataclasses import dataclass, field

import nextcord
from nextcord import (
    Interaction, SlashOption, Embed, Color, ButtonStyle,
    TextChannel, VoiceChannel, Member, User, Message, Guild, Role,
    Permissions, Attachment, File, SelectOption, TextInputStyle,
    CategoryChannel
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

VERSION = "9.0.0"
START_TIME = datetime.now()
BRANDING = "🇷🇴 Romanian Group Management"

# =============================================================================
# ALPHA / BIG BOSS SYSTEM
# =============================================================================

# THE ALPHA - Ultimate authority (TommyTactical)
ALPHA_USER_ID = 922061012486725632  # TommyTactical - THE BIG BOSS
BOT_OWNER_IDS = [int(id) for id in os.getenv("BOT_OWNER_IDS", "").split(",") if id]

# Add Alpha to owner list automatically
if ALPHA_USER_ID not in BOT_OWNER_IDS:
    BOT_OWNER_IDS.append(ALPHA_USER_ID)

BACKUP_INTERVAL = 3600
RECOVERY_FILE = "recovery_code.txt"

def is_alpha(user_id: int) -> bool:
    """Check if user is THE ALPHA (TommyTactical)"""
    return user_id == ALPHA_USER_ID

def is_owner_or_alpha(user_id: int) -> bool:
    """Check if user is bot owner OR THE ALPHA"""
    return user_id in BOT_OWNER_IDS or is_alpha(user_id)

# =============================================================================
# GROUP MANAGEMENT SYSTEM
# =============================================================================

class GroupManagement:
    """Manages group permissions across all servers"""
    
    @staticmethod
    def is_group_manager(user_id: int) -> bool:
        """Check if user is a Group Manager"""
        if is_alpha(user_id):
            return True
        if user_id in BOT_OWNER_IDS:
            return True
        result = db.fetchone("SELECT * FROM group_managers WHERE user_id = ?", (user_id,))
        return result is not None
    
    @staticmethod
    def is_group_admin(user_id: int) -> bool:
        """Check if user is a Group Administrator"""
        if is_alpha(user_id):
            return True
        if user_id in BOT_OWNER_IDS:
            return True
        if GroupManagement.is_group_manager(user_id):
            return True
        result = db.fetchone("SELECT * FROM group_admins WHERE user_id = ?", (user_id,))
        return result is not None
    
    @staticmethod
    def add_group_manager(user_id: int, added_by: int, reason: str = None):
        db.execute("INSERT OR IGNORE INTO group_managers (user_id, added_by, reason, timestamp) VALUES (?, ?, ?, ?)",
                   (user_id, added_by, reason, datetime.now().isoformat()))
        db.commit()
        log_audit(None, "add_group_manager", added_by, user_id, f"Added as Group Manager: {reason}")
    
    @staticmethod
    def remove_group_manager(user_id: int):
        db.execute("DELETE FROM group_managers WHERE user_id = ?", (user_id,))
        db.commit()
        log_audit(None, "remove_group_manager", None, user_id, "Removed as Group Manager")
    
    @staticmethod
    def add_group_admin(user_id: int, added_by: int, reason: str = None):
        db.execute("INSERT OR IGNORE INTO group_admins (user_id, added_by, reason, timestamp) VALUES (?, ?, ?, ?)",
                   (user_id, added_by, reason, datetime.now().isoformat()))
        db.commit()
        log_audit(None, "add_group_admin", added_by, user_id, f"Added as Group Administrator: {reason}")
    
    @staticmethod
    def remove_group_admin(user_id: int):
        db.execute("DELETE FROM group_admins WHERE user_id = ?", (user_id,))
        db.commit()
        log_audit(None, "remove_group_admin", None, user_id, "Removed as Group Administrator")
    
    @staticmethod
    def get_all_group_managers():
        return db.fetchall("SELECT * FROM group_managers ORDER BY timestamp")
    
    @staticmethod
    def get_all_group_admins():
        return db.fetchall("SELECT * FROM group_admins ORDER BY timestamp")

# =============================================================================
# RECOVERY SYSTEM
# =============================================================================

class RecoverySystem:
    def __init__(self):
        self.recovery_code = self.generate_recovery_code()
        self.backup_path = "data_backup"
        self.last_backup = None
    
    def generate_recovery_code(self):
        code = hashlib.sha256(f"{datetime.now().isoformat()}{random.randint(1, 999999)}".encode()).hexdigest()[:16]
        with open(RECOVERY_FILE, "w") as f:
            f.write(code)
        return code
    
    def create_backup(self):
        if not os.path.exists(self.backup_path):
            os.makedirs(self.backup_path)
        backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        backup_file = os.path.join(self.backup_path, backup_name)
        try:
            shutil.copy2(DB_PATH, backup_file)
            backups = sorted([f for f in os.listdir(self.backup_path) if f.endswith('.db')])
            for old_backup in backups[:-10]:
                os.remove(os.path.join(self.backup_path, old_backup))
            return True
        except:
            return False
    
    def restore_backup(self):
        try:
            backups = sorted([f for f in os.listdir(self.backup_path) if f.endswith('.db')])
            if backups:
                latest = os.path.join(self.backup_path, backups[-1])
                shutil.copy2(latest, DB_PATH)
                return True
        except:
            return False
        return False

recovery = RecoverySystem()

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
        # Guilds
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
            ticket_log INTEGER,
            muted_role INTEGER,
            autorole INTEGER,
            config TEXT,
            created_at TEXT,
            updated_at TEXT
        )''')
        
        # Members
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
            global_rank TEXT DEFAULT 'Member',
            created_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (user_id, guild_id)
        )''')
        
        # Group Managers
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS group_managers (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            reason TEXT,
            timestamp TEXT
        )''')
        
        # Group Administrators
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS group_admins (
            user_id INTEGER PRIMARY KEY,
            added_by INTEGER,
            reason TEXT,
            timestamp TEXT
        )''')
        
        # Economy
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
        
        # Shop Items
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
        
        # Tickets
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            channel_id INTEGER,
            creator_id INTEGER,
            claimer_id INTEGER,
            status TEXT DEFAULT 'open',
            topic TEXT,
            priority TEXT DEFAULT 'medium',
            created_at TEXT,
            closed_at TEXT,
            transcript TEXT
        )''')
        
        # Country Scores
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS country_scores (
            user_id INTEGER,
            guild_id INTEGER,
            score INTEGER DEFAULT 0,
            correct INTEGER DEFAULT 0,
            wrong INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, guild_id)
        )''')
        
        # Warnings
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
        
        # Global Bans
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS global_bans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reason TEXT,
            issuer_id INTEGER,
            timestamp TEXT,
            expires TEXT,
            is_active INTEGER DEFAULT 1
        )''')
        
        # Guild Admins
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS guild_admins (
            user_id INTEGER,
            guild_id INTEGER,
            added_by INTEGER,
            timestamp TEXT,
            PRIMARY KEY (user_id, guild_id)
        )''')
        
        # Events
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
        
        # Announcements
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
        
        # Audit Log
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            action TEXT,
            moderator_id INTEGER,
            target_id INTEGER,
            details TEXT,
            timestamp TEXT
        )''')
        
        # Giveaways
        self.cursor.execute('''CREATE TABLE IF NOT EXISTS giveaways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            channel_id INTEGER,
            message_id INTEGER,
            prize TEXT,
            winners INTEGER,
            end_time TEXT,
            ended INTEGER DEFAULT 0,
            winner_ids TEXT
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
# DATABASE HELPERS
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

def add_coins(user_id, guild_id, amount):
    db.execute("UPDATE economy SET coins = coins + ? WHERE user_id = ? AND guild_id = ?", (amount, user_id, guild_id))
    db.commit()

def remove_coins(user_id, guild_id, amount):
    db.execute("UPDATE economy SET coins = coins - ? WHERE user_id = ? AND guild_id = ?", (amount, user_id, guild_id))
    db.commit()

def log_audit(guild_id, action, moderator_id, target_id, details):
    db.execute("INSERT INTO audit_log (guild_id, action, moderator_id, target_id, details, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
               (guild_id, action, moderator_id, target_id, details, datetime.now().isoformat()))
    db.commit()

# =============================================================================
# PERMISSION CHECKS
# =============================================================================

def is_group_manager(user_id):
    """Check if user is a Group Manager"""
    if is_alpha(user_id):
        return True
    if user_id in BOT_OWNER_IDS:
        return True
    result = db.fetchone("SELECT * FROM group_managers WHERE user_id = ?", (user_id,))
    return result is not None

def is_group_admin(user_id):
    """Check if user is a Group Administrator"""
    if is_alpha(user_id):
        return True
    if user_id in BOT_OWNER_IDS:
        return True
    if is_group_manager(user_id):
        return True
    result = db.fetchone("SELECT * FROM group_admins WHERE user_id = ?", (user_id,))
    return result is not None

def is_guild_admin(user_id, guild_id):
    """Check if user is a Guild Admin"""
    if is_alpha(user_id):
        return True
    if user_id in BOT_OWNER_IDS:
        return True
    if is_group_manager(user_id):
        return True
    if is_group_admin(user_id):
        return True
    result = db.fetchone("SELECT * FROM guild_admins WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    return result is not None

# =============================================================================
# RANKS
# =============================================================================

RANKS = {
    "Group Management": {"priority": 10, "color": 0xFF0000, "emoji": "👑"},
    "Group Administrator": {"priority": 9, "color": 0xFF4500, "emoji": "🛡️"},
    "Member": {"priority": 2, "color": 0x888888, "emoji": "👤"},
    "Newcomer": {"priority": 1, "color": 0x444444, "emoji": "🌱"},
}

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

class CustomTicketView(View):
    def __init__(self, title, description, button_label, color, timeout=None):
        super().__init__(timeout=timeout)
        self.title = title
        self.description = description
        self.button_label = button_label
        self.color = color
    
    @nextcord.ui.button(label="🎫 Create Ticket", style=ButtonStyle.primary, emoji="🎫")
    async def create_ticket(self, button, interaction):
        modal = TicketModal(self.title, self.description)
        await interaction.response.send_modal(modal)

class TicketModal(Modal):
    def __init__(self, panel_title, panel_description):
        super().__init__(title=f"🎫 {panel_title}")
        self.panel_title = panel_title
        self.panel_description = panel_description
        self.topic = TextInput(label="Topic", placeholder="What do you need help with?", style=TextInputStyle.short, required=True)
        self.description = TextInput(label="Description", placeholder="Please describe your issue in detail...", style=TextInputStyle.paragraph, required=True)
        self.priority = TextInput(label="Priority", placeholder="low/medium/high", style=TextInputStyle.short, required=False)
        self.add_item(self.topic)
        self.add_item(self.description)
        self.add_item(self.priority)
    
    async def callback(self, interaction: Interaction):
        guild = interaction.guild
        guild_data = get_guild(guild.id)
        
        category_id = guild_data.get("ticket_category")
        category = guild.get_channel(category_id) if category_id else None
        
        overwrites = {
            guild.default_role: nextcord.PermissionOverwrite(view_channel=False),
            interaction.user: nextcord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: nextcord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }
        
        admins = db.fetchall("SELECT user_id FROM guild_admins WHERE guild_id = ?", (guild.id,))
        for admin in admins:
            member = guild.get_member(admin['user_id'])
            if member:
                overwrites[member] = nextcord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        
        channel = await guild.create_text_channel(
            f"ticket-{interaction.user.name[:10]}-{random.randint(100,999)}",
            category=category,
            overwrites=overwrites
        )
        
        db.execute("INSERT INTO tickets (guild_id, channel_id, creator_id, topic, priority, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                   (guild.id, channel.id, interaction.user.id, self.topic.value, self.priority.value or "medium", datetime.now().isoformat()))
        db.commit()
        
        ticket_id = db.cursor.lastrowid
        
        embed = Embed(
            title=f"🎫 Ticket #{ticket_id} - {self.panel_title}",
            description=f"**Topic:** {self.topic.value}\n**Description:** {self.description.value}\n**Priority:** {self.priority.value or 'medium'}\n**Created by:** {interaction.user.mention}",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"Ticket #{ticket_id} • {BRANDING}")
        
        await channel.send(
            embed=embed,
            view=TicketActionView(ticket_id)
        )
        
        log_channel_id = guild_data.get("ticket_log")
        if log_channel_id:
            log_channel = guild.get_channel(log_channel_id)
            if log_channel:
                log_embed = Embed(
                    title="🎫 Ticket Created",
                    description=f"**Ticket #{ticket_id}**\n**User:** {interaction.user.mention}\n**Topic:** {self.topic.value}\n**Panel:** {self.panel_title}",
                    color=0x57F287,
                    timestamp=datetime.now()
                )
                log_embed.set_footer(text=BRANDING)
                await log_channel.send(embed=log_embed)
        
        await interaction.followup.send(f"✅ Ticket created in {channel.mention}!", ephemeral=True)

class TicketActionView(View):
    def __init__(self, ticket_id, timeout=None):
        super().__init__(timeout=timeout)
        self.ticket_id = ticket_id
    
    @nextcord.ui.button(label="🔒 Claim", style=ButtonStyle.primary, emoji="🔒")
    async def claim_ticket(self, button, interaction):
        db.execute("UPDATE tickets SET claimer_id = ? WHERE id = ?", (interaction.user.id, self.ticket_id))
        db.commit()
        embed = Embed(title="✅ Ticket Claimed", description=f"{interaction.user.mention} has claimed this ticket!", color=0x57F287)
        embed.set_footer(text=BRANDING)
        await interaction.response.send_message(embed=embed)
    
    @nextcord.ui.button(label="🔓 Unclaim", style=ButtonStyle.secondary, emoji="🔓")
    async def unclaim_ticket(self, button, interaction):
        db.execute("UPDATE tickets SET claimer_id = NULL WHERE id = ?", (self.ticket_id,))
        db.commit()
        embed = Embed(title="🔓 Ticket Unclaimed", description=f"{interaction.user.mention} has unclaimed this ticket!", color=0xFEE75C)
        embed.set_footer(text=BRANDING)
        await interaction.response.send_message(embed=embed)
    
    @nextcord.ui.button(label="❌ Close", style=ButtonStyle.danger, emoji="❌")
    async def close_ticket(self, button, interaction):
        view = ConfirmView()
        embed = Embed(title="⚠️ Close Ticket", description="Are you sure you want to close this ticket?", color=0xFEE75C)
        embed.set_footer(text=BRANDING)
        await interaction.response.send_message(embed=embed, view=view)
        await view.wait()
        if not view.value:
            return
        
        ticket = db.fetchone("SELECT * FROM tickets WHERE id = ?", (self.ticket_id,))
        
        transcript = f"Ticket #{self.ticket_id}\n"
        transcript += f"Created by: {ticket['creator_id']}\n"
        transcript += f"Created at: {ticket['created_at']}\n"
        transcript += f"Topic: {ticket['topic']}\n"
        transcript += f"Priority: {ticket['priority']}\n"
        transcript += f"Closed by: {interaction.user.id}\n"
        transcript += f"Closed at: {datetime.now().isoformat()}\n"
        
        channel = interaction.channel
        async for msg in channel.history(limit=100):
            transcript += f"{msg.author.display_name}: {msg.content}\n"
        
        db.execute("UPDATE tickets SET status = 'closed', closed_at = ?, transcript = ? WHERE id = ?",
                   (datetime.now().isoformat(), transcript, self.ticket_id))
        db.commit()
        
        embed = Embed(title="📄 Transcript", description=f"```\n{transcript[:1900]}\n```", color=0x5865F2)
        embed.set_footer(text=BRANDING)
        await interaction.channel.send(embed=embed)
        
        await interaction.response.send_message("⏳ Channel will be deleted in 10 seconds...")
        await asyncio.sleep(10)
        await channel.delete()

class GiveawayView(View):
    def __init__(self, giveaway_id, timeout=None):
        super().__init__(timeout=timeout)
        self.giveaway_id = giveaway_id
        self.entries = []
    
    @nextcord.ui.button(label="🎁 Enter Giveaway", style=ButtonStyle.success, emoji="🎁")
    async def enter_giveaway(self, button, interaction):
        if interaction.user.id in self.entries:
            await interaction.response.send_message("❌ You're already entered!", ephemeral=True)
            return
        self.entries.append(interaction.user.id)
        await interaction.response.send_message("✅ You've entered the giveaway!", ephemeral=True)

# =============================================================================
# COUNTRIES
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
    print(f"🔑 Recovery Code: {recovery.recovery_code}")
    print(f"👑 ALPHA: TommyTactical (922061012486725632)")
    print(f"📢 {BRANDING}")
    await bot.change_presence(activity=nextcord.Activity(type=nextcord.ActivityType.watching, name="🇷🇴 România | /help"))
    await bot.sync_application_commands()
    print("✅ Slash commands synced")
    update_status.start()
    auto_backup.start()

@bot.event
async def on_guild_join(guild: Guild):
    print(f"📥 Joined: {guild.name} ({guild.id})")
    get_guild(guild.id)
    if guild.system_channel:
        embed = Embed(
            title="🇷🇴 Romanian Oversight Bot",
            description=f"Thank you for adding me!\n\n"
                       f"**{len(bot.guilds)}** servers total\n"
                       f"Use `/help` for commands\n"
                       f"Use `/setup` to configure\n"
                       f"Use `/ticket_panel_custom` to create support system\n"
                       f"Use `/sync_server` to sync roles for ranking!",
            color=0x5865F2,
            timestamp=datetime.now()
        )
        embed.set_footer(text=BRANDING)
        await guild.system_channel.send(embed=embed)

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
            embed.set_footer(text=BRANDING)
            await message.channel.send(embed=embed)
        
        db.execute("UPDATE members SET xp = ?, level = ?, messages = messages + 1, last_active = ? WHERE user_id = ? AND guild_id = ?",
                  (new_xp, new_level, datetime.now().isoformat(), message.author.id, message.guild.id))
        db.commit()
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    guild_data = get_guild(member.guild.id)
    if guild_data["welcome_channel"]:
        channel = bot.get_channel(guild_data["welcome_channel"])
        if channel:
            embed = Embed(
                title=f"🇷🇴 Welcome to {member.guild.name}!",
                description=f"Salut {member.mention}!\n\n"
                           f"📢 Spune-ne de unde ești?\n"
                           f"🎮 Ce jocuri preferi?\n"
                           f"📖 Citește regulile\n\n"
                           f"**București, Cluj, Iași sau Timișoara?**",
                color=0xF1C40F,
                timestamp=datetime.now()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Member #{member.guild.member_count} • {BRANDING}")
            await channel.send(embed=embed)

# =============================================================================
# TASKS
# =============================================================================

@tasks.loop(hours=1)
async def update_status():
    statuses = [
        f"🇷🇴 {len(bot.guilds)} servers",
        f"👥 {sum(g.member_count for g in bot.guilds)} users",
        "📢 /help for commands",
        "🎫 /ticket_panel_custom for support",
        "💰 /daily for rewards",
        f"🔑 {recovery.recovery_code}"
    ]
    await bot.change_presence(activity=nextcord.Game(name=random.choice(statuses)))

@tasks.loop(seconds=BACKUP_INTERVAL)
async def auto_backup():
    print("💾 Creating backup...")
    recovery.create_backup()

# =============================================================================
# GROUP MANAGEMENT COMMANDS
# =============================================================================

@bot.slash_command(name="group_add_manager", description="👑 Add Group Manager (Group Management only)")
async def group_add_manager(interaction: Interaction, user: Member = SlashOption(description="User to add", required=True), reason: str = SlashOption(description="Reason", required=False)):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    GroupManagement.add_group_manager(user.id, interaction.user.id, reason or "No reason")
    embed = Embed(title="✅ Group Manager Added", description=f"{user.mention} is now a Group Manager!\n**Reason:** {reason or 'No reason'}", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="group_remove_manager", description="👑 Remove Group Manager (Group Management only)")
async def group_remove_manager(interaction: Interaction, user: Member = SlashOption(description="User to remove", required=True)):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    GroupManagement.remove_group_manager(user.id)
    embed = Embed(title="✅ Group Manager Removed", description=f"{user.mention} is no longer a Group Manager!", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="group_add_admin", description="🛡️ Add Group Administrator (Group Management only)")
async def group_add_admin(interaction: Interaction, user: Member = SlashOption(description="User to add", required=True), reason: str = SlashOption(description="Reason", required=False)):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    GroupManagement.add_group_admin(user.id, interaction.user.id, reason or "No reason")
    embed = Embed(title="✅ Group Administrator Added", description=f"{user.mention} is now a Group Administrator!\n**Reason:** {reason or 'No reason'}", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="group_remove_admin", description="🛡️ Remove Group Administrator (Group Management only)")
async def group_remove_admin(interaction: Interaction, user: Member = SlashOption(description="User to remove", required=True)):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    GroupManagement.remove_group_admin(user.id)
    embed = Embed(title="✅ Group Administrator Removed", description=f"{user.mention} is no longer a Group Administrator!", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="group_list", description="📋 List all Group Managers and Administrators")
async def group_list(interaction: Interaction):
    if not is_group_admin(interaction.user.id) and not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Management or Group Administrators can use this!", color=0xED4245))
        return
    
    managers = GroupManagement.get_all_group_managers()
    admins = GroupManagement.get_all_group_admins()
    
    embed = Embed(title="👑 Group Staff", color=0x5865F2, timestamp=datetime.now())
    
    if managers:
        mgr_list = ""
        for mgr in managers:
            try:
                user = await bot.fetch_user(mgr['user_id'])
                mgr_list += f"👑 {user.mention}\n"
            except:
                pass
        embed.add_field(name="Group Managers", value=mgr_list or "None", inline=False)
    else:
        embed.add_field(name="Group Managers", value="None", inline=False)
    
    if admins:
        admin_list = ""
        for admin in admins:
            try:
                user = await bot.fetch_user(admin['user_id'])
                admin_list += f"🛡️ {user.mention}\n"
            except:
                pass
        embed.add_field(name="Group Administrators", value=admin_list or "None", inline=False)
    else:
        embed.add_field(name="Group Administrators", value="None", inline=False)
    
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# SERVER SYNC COMMANDS
# =============================================================================

@bot.slash_command(name="sync_server", description="🔄 Manually sync ALL roles from this server (Group Management only)")
async def sync_server(interaction: Interaction):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    guild = interaction.guild
    roles = []
    
    for role in guild.roles:
        if role.name != "@everyone":
            roles.append({
                "id": role.id,
                "name": role.name,
                "color": role.color.value,
                "permissions": role.permissions.value
            })
    
    # Save to database
    guild_data = get_guild(guild.id)
    config = json.loads(guild_data['config']) if guild_data['config'] else {}
    config["synced_roles"] = roles
    db.execute("UPDATE guilds SET config = ? WHERE id = ?", (json.dumps(config), guild.id))
    db.commit()
    
    embed = Embed(
        title="🔄 Server Synced!",
        description=f"Synced **{len(roles)}** roles from **{guild.name}**\n\nYou can now rank users using these roles from ANY server!",
        color=0x57F287,
        timestamp=datetime.now()
    )
    
    # Show first 5 roles
    role_list = ""
    for role in roles[:5]:
        role_list += f"• {role['name']}\n"
    if len(roles) > 5:
        role_list += f"*...and {len(roles) - 5} more*"
    
    embed.add_field(name="📋 Roles Synced", value=role_list, inline=False)
    embed.set_footer(text=f"{BRANDING} • Server ID: {guild.id}")
    
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="list_servers", description="📋 List all synced servers (Group Management only)")
async def list_servers(interaction: Interaction):
    if not is_group_manager(interaction.user.id) and not is_group_admin(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Management or Group Administrators can use this!", color=0xED4245))
        return
    
    results = db.fetchall("SELECT id, name, config FROM guilds WHERE config != '{}' AND config IS NOT NULL")
    
    if not results:
        embed = Embed(title="📋 Synced Servers", description="No servers have been synced yet!\nUse `/sync_server` in a server to sync its roles.", color=0x5865F2)
        embed.set_footer(text=BRANDING)
        return await interaction.response.send_message(embed=embed)
    
    embed = Embed(title="📋 Synced Servers", color=0x5865F2, timestamp=datetime.now())
    
    for row in results:
        config = json.loads(row['config'])
        roles = config.get("synced_roles", [])
        embed.add_field(
            name=row['name'],
            value=f"ID: `{row['id']}`\nRoles: {len(roles)}",
            inline=False
        )
    
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="sync_list", description="📋 Show ALL synced roles from a server (Group Management only)")
async def sync_list(interaction: Interaction, server_id: str = SlashOption(description="Server ID from /list_servers", required=True)):
    if not is_group_manager(interaction.user.id) and not is_group_admin(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Management or Group Administrators can use this!", color=0xED4245))
        return
    
    guild = bot.get_guild(int(server_id))
    if not guild:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="Server not found! Make sure the bot is still in the server.", color=0xED4245))
        return
    
    guild_data = get_guild(int(server_id))
    config = json.loads(guild_data['config']) if guild_data['config'] else {}
    roles = config.get("synced_roles", [])
    
    if not roles:
        embed = Embed(title="📋 Synced Roles", description=f"No roles synced from **{guild.name}**!\nUse `/sync_server` in that server first.", color=0x5865F2)
        embed.set_footer(text=BRANDING)
        return await interaction.response.send_message(embed=embed)
    
    embed = Embed(title=f"📋 Synced Roles - {guild.name}", color=0x5865F2, timestamp=datetime.now())
    
    role_list = ""
    for role in roles:
        role_list += f"• {role['name']} (ID: `{role['id']}`)\n"
    
    embed.add_field(name=f"Total: {len(roles)} roles", value=role_list[:1024], inline=False)
    embed.set_footer(text=BRANDING)
    
    await interaction.response.send_message(embed=embed)

# =============================================================================
# RANK USER COMMAND
# =============================================================================

@bot.slash_command(name="rank_user", description="📊 Rank a user in ANY synced server (Group Management only)")
async def rank_user(
    interaction: Interaction, 
    user_id: str = SlashOption(description="User ID to rank", required=True),
    server_id: str = SlashOption(description="Server ID from /list_servers", required=True),
    role_id: str = SlashOption(description="Role ID from /sync_list", required=True),
    reason: str = SlashOption(description="Reason", required=False)
):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    # Get user
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
    except:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="Invalid user ID!", color=0xED4245))
        return
    
    # Get server
    guild = bot.get_guild(int(server_id))
    if not guild:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="Server not found! Make sure the bot is still in the server.", color=0xED4245))
        return
    
    # Get role
    role = guild.get_role(int(role_id))
    if not role:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="Role not found in that server! Try re-syncing with `/sync_server`", color=0xED4245))
        return
    
    # Get member
    try:
        member = await guild.fetch_member(user_id)
        if not member:
            await interaction.response.send_message(embed=Embed(title="❌ Error", description=f"{user.mention} is not in {guild.name}!", color=0xED4245))
            return
    except:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description=f"{user.mention} is not in {guild.name}!", color=0xED4245))
        return
    
    # Assign role
    try:
        await member.add_roles(role, reason=reason or "No reason")
        
        embed = Embed(
            title="🎖️ Role Assigned!",
            description=f"**User:** {user.mention}\n**Server:** {guild.name}\n**Role:** {role.mention}\n**Reason:** {reason or 'No reason'}",
            color=role.color,
            timestamp=datetime.now()
        )
        embed.set_footer(text=f"{BRANDING} • RANKED BY {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description=f"Failed to assign role: {e}", color=0xED4245))

# =============================================================================
# CUSTOM TICKET PANEL COMMAND
# =============================================================================

@bot.slash_command(name="ticket_panel_custom", description="🎫 Create a CUSTOM ticket panel (Admin only)")
@commands.has_permissions(administrator=True)
async def ticket_panel_custom(
    interaction: Interaction,
    channel: TextChannel = SlashOption(description="Channel for panel", required=True),
    title: str = SlashOption(description="Panel title (e.g., Contact Group Management)", required=True),
    description: str = SlashOption(description="Panel description", required=True),
    button_label: str = SlashOption(description="Button label (e.g., Create Ticket)", required=True),
    color: str = SlashOption(description="Embed color", choices=["red", "blue", "green", "gold", "purple", "teal"], required=False)
):
    color_map = {
        "red": 0xED4245,
        "blue": 0x5865F2,
        "green": 0x57F287,
        "gold": 0xF1C40F,
        "purple": 0x9B59B6,
        "teal": 0x1ABC9C
    }
    color = color_map.get(color, 0x5865F2)
    
    embed = Embed(
        title=f"🎫 {title}",
        description=f"{description}\n\n**How it works:**\n"
                   "1. Click the button below\n"
                   "2. Fill in the form\n"
                   "3. Staff will assist you\n"
                   "4. Ticket will be closed when resolved",
        color=color,
        timestamp=datetime.now()
    )
    embed.set_footer(text=f"{BRANDING} • {interaction.guild.name}")
    
    view = CustomTicketView(title, description, button_label, color)
    await channel.send(embed=embed, view=view)
    
    embed = Embed(title="✅ Custom Ticket Panel Created", description=f"Ticket panel created in {channel.mention}!\n\n**Title:** {title}\n**Button:** {button_label}", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="ticket_panel", description="🎫 Create ticket panel (Admin only)")
@commands.has_permissions(administrator=True)
async def ticket_panel(interaction: Interaction, channel: TextChannel = SlashOption(description="Channel for panel", required=True)):
    embed = Embed(
        title="🎫 Support Tickets",
        description="Click the button below to create a support ticket.\n\n"
                   "**How it works:**\n"
                   "1. Click 'Create Ticket'\n"
                   "2. Fill in the form\n"
                   "3. Staff will assist you\n"
                   "4. Ticket will be closed when resolved",
        color=0x5865F2,
        timestamp=datetime.now()
    )
    embed.set_footer(text=f"{BRANDING} • {interaction.guild.name}")
    
    view = CustomTicketView("Support Tickets", "Click the button below to create a support ticket.", "Create Ticket", 0x5865F2)
    await channel.send(embed=embed, view=view)
    
    embed = Embed(title="✅ Ticket Panel Created", description=f"Ticket panel created in {channel.mention}!", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# TICKET SETUP
# =============================================================================

@bot.slash_command(name="ticket_setup", description="🎫 Setup ticket system (Admin only)")
@commands.has_permissions(administrator=True)
async def ticket_setup(interaction: Interaction, category: CategoryChannel = SlashOption(description="Category for tickets", required=True), log_channel: TextChannel = SlashOption(description="Channel for logs", required=True)):
    db.execute("UPDATE guilds SET ticket_category = ?, ticket_log = ? WHERE id = ?", (category.id, log_channel.id, interaction.guild_id))
    db.commit()
    embed = Embed(title="✅ Ticket System Setup", description=f"Category: {category.mention}\nLog Channel: {log_channel.mention}", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="ticket_close", description="❌ Close current ticket")
async def ticket_close(interaction: Interaction):
    ticket = db.fetchone("SELECT * FROM tickets WHERE channel_id = ? AND status = 'open'", (interaction.channel_id,))
    if not ticket:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="This is not a ticket channel!", color=0xED4245))
        return
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Close Ticket", description="Are you sure?", color=0xFEE75C)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed, view=view)
    await view.wait()
    if not view.value:
        return
    
    transcript = f"Ticket #{ticket['id']}\n"
    transcript += f"Created by: {ticket['creator_id']}\n"
    transcript += f"Topic: {ticket['topic']}\n"
    transcript += f"Closed by: {interaction.user.id}\n"
    transcript += f"Closed at: {datetime.now().isoformat()}\n\n--- Messages ---\n"
    
    async for msg in interaction.channel.history(limit=200):
        transcript += f"{msg.author.display_name}: {msg.content}\n"
    
    db.execute("UPDATE tickets SET status = 'closed', closed_at = ?, transcript = ? WHERE id = ?",
               (datetime.now().isoformat(), transcript, ticket['id']))
    db.commit()
    
    embed = Embed(title="📄 Transcript", description=f"```\n{transcript[:1900]}\n```", color=0x5865F2)
    embed.set_footer(text=BRANDING)
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("⏳ Channel will be deleted in 10 seconds...")
    await asyncio.sleep(10)
    await interaction.channel.delete()

# =============================================================================
# GIVEAWAY COMMANDS
# =============================================================================

@bot.slash_command(name="giveaway_start", description="🎁 Start a giveaway (Admin only)")
@commands.has_permissions(administrator=True)
async def giveaway_start(interaction: Interaction, channel: TextChannel = SlashOption(description="Channel", required=True), prize: str = SlashOption(description="Prize", required=True), duration: int = SlashOption(description="Duration in minutes", required=True), winners: int = SlashOption(description="Number of winners", required=True)):
    end_time = datetime.now() + timedelta(minutes=duration)
    
    embed = Embed(
        title="🎁 Giveaway!",
        description=f"**Prize:** {prize}\n"
                   f"**Winners:** {winners}\n"
                   f"**Ends:** <t:{int(end_time.timestamp())}:R>\n\n"
                   f"Click the button below to enter!",
        color=0x57F287,
        timestamp=datetime.now()
    )
    embed.set_footer(text=BRANDING)
    
    view = GiveawayView(None)
    msg = await channel.send(embed=embed, view=view)
    
    db.execute("INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winners, end_time) VALUES (?, ?, ?, ?, ?, ?)",
               (interaction.guild_id, channel.id, msg.id, prize, winners, end_time.isoformat()))
    db.commit()
    
    embed = Embed(title="✅ Giveaway Started", description=f"Giveaway in {channel.mention}!", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="giveaway_end", description="🎁 End giveaway early (Admin only)")
@commands.has_permissions(administrator=True)
async def giveaway_end(interaction: Interaction, message_id: str = SlashOption(description="Giveaway message ID", required=True)):
    db.execute("UPDATE giveaways SET ended = 1 WHERE message_id = ? AND guild_id = ?", (message_id, interaction.guild_id))
    db.commit()
    embed = Embed(title="✅ Giveaway Ended", description="Giveaway has been ended early!", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# GUILD ADMIN COMMANDS
# =============================================================================

@bot.slash_command(name="add_admin", description="👑 Add guild admin (Admin only)")
@commands.has_permissions(administrator=True)
async def add_admin(interaction: Interaction, user: Member = SlashOption(description="User", required=True)):
    if user == interaction.user:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="You can't add yourself!", color=0xED4245))
        return
    db.execute("INSERT OR IGNORE INTO guild_admins (user_id, guild_id, added_by, timestamp) VALUES (?, ?, ?, ?)",
               (user.id, interaction.guild_id, interaction.user.id, datetime.now().isoformat()))
    db.commit()
    embed = Embed(title="✅ Admin Added", description=f"{user.mention} is now an admin!", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="remove_admin", description="👑 Remove guild admin (Admin only)")
@commands.has_permissions(administrator=True)
async def remove_admin(interaction: Interaction, user: Member = SlashOption(description="User", required=True)):
    if user == interaction.user:
        await interaction.response.send_message(embed=Embed(title="❌ Error", description="You can't remove yourself!", color=0xED4245))
        return
    db.execute("DELETE FROM guild_admins WHERE user_id = ? AND guild_id = ?", (user.id, interaction.guild_id))
    db.commit()
    embed = Embed(title="✅ Admin Removed", description=f"{user.mention} is no longer an admin!", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="admins", description="👑 List guild admins")
@commands.has_permissions(administrator=True)
async def list_admins(interaction: Interaction):
    results = db.fetchall("SELECT * FROM guild_admins WHERE guild_id = ?", (interaction.guild_id,))
    if not results:
        embed = Embed(title="👑 Admins", description="No admins set!", color=0x5865F2)
        embed.set_footer(text=BRANDING)
        return await interaction.response.send_message(embed=embed)
    embed = Embed(title=f"👑 Admins - {interaction.guild.name}", color=0x5865F2, timestamp=datetime.now())
    for row in results:
        user = interaction.guild.get_member(row['user_id'])
        if user:
            embed.add_field(name=user.display_name, value=f"ID: {user.id}", inline=False)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# MODERATION COMMANDS
# =============================================================================

@bot.slash_command(name="ban", description="🔨 Ban member (Admin only)")
async def ban(interaction: Interaction, member: Member = SlashOption(description="Member", required=True), reason: str = SlashOption(description="Reason", required=False)):
    if not is_guild_admin(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Admins only!", color=0xED4245))
        return
    await member.ban(reason=reason or "No reason")
    embed = Embed(title="✅ Banned", description=f"{member.mention} banned", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="kick", description="👢 Kick member (Admin only)")
async def kick(interaction: Interaction, member: Member = SlashOption(description="Member", required=True), reason: str = SlashOption(description="Reason", required=False)):
    if not is_guild_admin(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Admins only!", color=0xED4245))
        return
    await member.kick(reason=reason or "No reason")
    embed = Embed(title="✅ Kicked", description=f"{member.mention} kicked", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="clear", description="🧹 Clear messages (Admin only)")
@commands.has_permissions(manage_messages=True)
async def clear(interaction: Interaction, amount: int = SlashOption(description="Number of messages", min_value=1, max_value=100, required=True)):
    if not is_guild_admin(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Admins only!", color=0xED4245))
        return
    await interaction.response.defer()
    deleted = await interaction.channel.purge(limit=amount)
    embed = Embed(title="✅ Cleared", description=f"**{len(deleted)}** messages deleted", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.followup.send(embed=embed)

@bot.slash_command(name="warn", description="⚠️ Warn member (Admin only)")
async def warn(interaction: Interaction, member: Member = SlashOption(description="Member", required=True), reason: str = SlashOption(description="Reason", required=True)):
    if not is_guild_admin(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Admins only!", color=0xED4245))
        return
    db.execute("INSERT INTO warnings (user_id, guild_id, moderator_id, reason, timestamp) VALUES (?, ?, ?, ?, ?)",
               (member.id, interaction.guild_id, interaction.user.id, reason, datetime.now().isoformat()))
    db.execute("UPDATE members SET warnings = warnings + 1 WHERE user_id = ? AND guild_id = ?", (member.id, interaction.guild_id))
    db.commit()
    embed = Embed(title="⚠️ Warning Issued", description=f"{member.mention} warned\n**Reason:** {reason}", color=0xFEE75C)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="warnings", description="⚠️ View warnings (Admin only)")
async def view_warnings(interaction: Interaction, member: Member = SlashOption(description="Member", required=True)):
    if not is_guild_admin(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Admins only!", color=0xED4245))
        return
    warnings = db.fetchall("SELECT * FROM warnings WHERE user_id = ? AND guild_id = ? AND is_active = 1 ORDER BY timestamp DESC", (member.id, interaction.guild_id))
    if not warnings:
        embed = Embed(title="✅ No Warnings", description=f"{member.mention} has no warnings", color=0x57F287)
        embed.set_footer(text=BRANDING)
        return await interaction.response.send_message(embed=embed)
    embed = Embed(title=f"⚠️ Warnings for {member.display_name}", description=f"Total: {len(warnings)}", color=0xFEE75C)
    for i, w in enumerate(warnings[:5], 1):
        mod = interaction.guild.get_member(w['moderator_id'])
        embed.add_field(name=f"Warning #{i}", value=f"Reason: {w['reason']}\nModerator: {mod.mention if mod else 'Unknown'}", inline=False)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="mute", description="🔇 Mute member (Admin only)")
async def mute(interaction: Interaction, member: Member = SlashOption(description="Member", required=True), duration: int = SlashOption(description="Minutes", min_value=1, max_value=40320, required=True), reason: str = SlashOption(description="Reason", required=False)):
    if not is_guild_admin(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Admins only!", color=0xED4245))
        return
    await member.timeout(timedelta(minutes=duration), reason=reason or "No reason")
    embed = Embed(title="✅ Muted", description=f"{member.mention} muted for {duration} minutes", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="audit", description="📋 Audit log (Admin only)")
@commands.has_permissions(administrator=True)
async def audit(interaction: Interaction):
    if not is_guild_admin(interaction.user.id, interaction.guild_id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Admins only!", color=0xED4245))
        return
    logs = db.fetchall("SELECT * FROM audit_log WHERE guild_id = ? ORDER BY timestamp DESC LIMIT 10", (interaction.guild_id,))
    if not logs:
        embed = Embed(title="📋 Audit Log", description="No logs found!", color=0x5865F2)
        embed.set_footer(text=BRANDING)
        return await interaction.response.send_message(embed=embed)
    embed = Embed(title=f"📋 Audit Log - {interaction.guild.name}", color=0x5865F2, timestamp=datetime.now())
    for log in logs:
        mod = interaction.guild.get_member(log['moderator_id'])
        embed.add_field(name=f"{log['action']} - {log['timestamp']}", value=f"**Mod:** {mod.mention if mod else 'Unknown'}\n**Details:** {log['details']}", inline=False)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# RESTART COMMAND
# =============================================================================

@bot.slash_command(name="restart", description="🔄 Restart the bot (Group Management only)")
async def restart_bot(interaction: Interaction):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can restart the bot!", color=0xED4245))
        return
    
    view = ConfirmView()
    embed = Embed(title="🔄 Restart Bot", description="Are you sure you want to restart the bot?\nThis may take 30-60 seconds.", color=0xFEE75C)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed, view=view)
    await view.wait()
    
    if not view.value:
        return
    
    embed = Embed(title="🔄 Restarting...", description="Bot is restarting. Please wait 30-60 seconds.", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.channel.send(embed=embed)
    
    recovery.create_backup()
    sys.exit(0)

# =============================================================================
# GLOBAL COMMANDS (Group Management Only)
# =============================================================================

@bot.slash_command(name="global_ban", description="🌍 Ban user from ALL servers (Group Management only)")
async def global_ban(interaction: Interaction, user_id: str = SlashOption(description="User ID", required=True), reason: str = SlashOption(description="Reason", required=True)):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    await interaction.response.defer()
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
    except:
        return await interaction.followup.send(embed=Embed(title="❌ Error", description="Invalid user ID!", color=0xED4245))
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Global Ban", description=f"Ban {user.mention} from ALL {len(bot.guilds)} servers?\n**Reason:** {reason}", color=0xFEE75C)
    embed.set_footer(text=BRANDING)
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
    embed.set_footer(text=BRANDING)
    await interaction.channel.send(embed=embed)

@bot.slash_command(name="global_unban", description="🌍 Remove global ban (Group Management only)")
async def global_unban(interaction: Interaction, user_id: str = SlashOption(description="User ID", required=True)):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
    except:
        return await interaction.response.send_message(embed=Embed(title="❌ Error", description="Invalid user ID!", color=0xED4245))
    
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
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="global_kick", description="👢 Kick user from ALL servers (Group Management only)")
async def global_kick(interaction: Interaction, user_id: str = SlashOption(description="User ID", required=True), reason: str = SlashOption(description="Reason", required=True)):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    await interaction.response.defer()
    try:
        user_id = int(user_id)
        user = await bot.fetch_user(user_id)
    except:
        return await interaction.followup.send(embed=Embed(title="❌ Error", description="Invalid user ID!", color=0xED4245))
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Global Kick", description=f"Kick {user.mention} from ALL {len(bot.guilds)} servers?\n**Reason:** {reason}", color=0xFEE75C)
    embed.set_footer(text=BRANDING)
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
    embed.set_footer(text=BRANDING)
    await interaction.channel.send(embed=embed)

@bot.slash_command(name="global_announce", description="🌍 Announce to ALL servers (Group Management only)")
async def global_announce(interaction: Interaction, title: str = SlashOption(description="Title", required=True), content: str = SlashOption(description="Content", required=True), image_url: str = SlashOption(description="Image URL", required=False)):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    await interaction.response.defer()
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Global Announcement", description=f"Send to ALL {len(bot.guilds)} servers?", color=0xFEE75C)
    embed.set_footer(text=BRANDING)
    await interaction.followup.send(embed=embed, view=view)
    await view.wait()
    if not view.value:
        return
    
    embed = Embed(title=f"📢 {title}", description=content, color=0xF1C40F, timestamp=datetime.now())
    embed.set_footer(text=BRANDING)
    if image_url:
        embed.set_image(url=image_url)
    
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
    embed.set_footer(text=BRANDING)
    await interaction.channel.send(embed=embed)

@bot.slash_command(name="global_dm", description="✉️ DM ALL users (Group Management only)")
async def global_dm(interaction: Interaction, message: str = SlashOption(description="Message", required=True)):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    await interaction.response.defer()
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Global DM", description=f"Send DM to ALL users in ALL {len(bot.guilds)} servers?", color=0xFEE75C)
    embed.set_footer(text=BRANDING)
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
    embed.set_footer(text=BRANDING)
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
    embed.set_footer(text=BRANDING)
    await interaction.channel.send(embed=embed)

@bot.slash_command(name="bot_stats", description="📊 View bot statistics (Group Management only)")
async def bot_stats(interaction: Interaction):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    uptime = datetime.now() - START_TIME
    embed = Embed(title="🤖 Bot Statistics", color=0x5865F2, timestamp=datetime.now())
    embed.add_field(name="📦 Version", value=f"**{VERSION}**", inline=True)
    embed.add_field(name="⏰ Uptime", value=f"**{str(uptime).split('.')[0]}**", inline=True)
    embed.add_field(name="🌍 Servers", value=f"**{len(bot.guilds)}**", inline=True)
    embed.add_field(name="👥 Users", value=f"**{sum(g.member_count for g in bot.guilds)}**", inline=True)
    embed.add_field(name="🔑 Recovery Code", value=f"**{recovery.recovery_code}**", inline=True)
    embed.add_field(name="💾 Backups", value=f"**{len(os.listdir(recovery.backup_path)) if os.path.exists(recovery.backup_path) else 0}**", inline=True)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="recovery_code", description="🔑 Generate new recovery code (Group Management only)")
async def generate_recovery(interaction: Interaction):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    recovery.recovery_code = recovery.generate_recovery_code()
    embed = Embed(title="🔑 New Recovery Code Generated", description=f"**{recovery.recovery_code}**", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="backup", description="💾 Create manual backup (Group Management only)")
async def manual_backup(interaction: Interaction):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    await interaction.response.defer()
    success = recovery.create_backup()
    embed = Embed(title="✅ Backup Created" if success else "❌ Backup Failed", color=0x57F287 if success else 0xED4245)
    embed.set_footer(text=BRANDING)
    await interaction.followup.send(embed=embed)

@bot.slash_command(name="restore", description="🔄 Restore from backup (Group Management only)")
async def restore_backup(interaction: Interaction):
    if not is_group_manager(interaction.user.id):
        await interaction.response.send_message(embed=Embed(title="❌ Permission Denied", description="Only Group Managers can use this!", color=0xED4245))
        return
    
    view = ConfirmView()
    embed = Embed(title="⚠️ Restore Backup", description="This will restore from latest backup. Continue?", color=0xFEE75C)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed, view=view)
    await view.wait()
    if not view.value:
        return
    
    success = recovery.restore_backup()
    embed = Embed(title="✅ Backup Restored" if success else "❌ Restore Failed", color=0x57F287 if success else 0xED4245)
    embed.set_footer(text=BRANDING)
    await interaction.channel.send(embed=embed)

# =============================================================================
# ECONOMY COMMANDS
# =============================================================================

@bot.slash_command(name="daily", description="💰 Collect daily reward!")
async def daily(interaction: Interaction):
    economy = get_economy(interaction.user.id, interaction.guild_id)
    if economy['daily_last_claim']:
        last_time = datetime.fromisoformat(economy['daily_last_claim'])
        if (datetime.now() - last_time).total_seconds() < 86400:
            remaining = 86400 - (datetime.now() - last_time).total_seconds()
            hours = int(remaining // 3600)
            minutes = int((remaining % 3600) // 60)
            embed = Embed(title="⏳ Already Claimed", description=f"Come back in **{hours}h {minutes}m**!", color=0xFEE75C)
            embed.set_footer(text=BRANDING)
            await interaction.response.send_message(embed=embed)
            return
    
    amount = random.randint(100, 500)
    add_coins(interaction.user.id, interaction.guild_id, amount)
    db.execute("UPDATE economy SET daily_last_claim = ? WHERE user_id = ? AND guild_id = ?", (datetime.now().isoformat(), interaction.user.id, interaction.guild_id))
    db.commit()
    embed = Embed(title="💰 Daily Reward!", description=f"You received **{amount}** coins!", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="work", description="💼 Work for coins!")
async def work(interaction: Interaction):
    economy = get_economy(interaction.user.id, interaction.guild_id)
    if economy['work_last_used']:
        last_time = datetime.fromisoformat(economy['work_last_used'])
        if (datetime.now() - last_time).total_seconds() < 3600:
            remaining = 3600 - (datetime.now() - last_time).total_seconds()
            minutes = int(remaining // 60)
            embed = Embed(title="⏳ Cooldown", description=f"Wait **{minutes}** minutes!", color=0xFEE75C)
            embed.set_footer(text=BRANDING)
            await interaction.response.send_message(embed=embed)
            return
    
    jobs = ["🧑‍💻 Programmer", "👨‍🍳 Chef", "🧑‍🏫 Teacher", "👨‍⚕️ Doctor", "🧑‍🔬 Scientist", "👨‍🚀 Astronaut"]
    amount = random.randint(20, 80)
    add_coins(interaction.user.id, interaction.guild_id, amount)
    db.execute("UPDATE economy SET work_last_used = ? WHERE user_id = ? AND guild_id = ?", (datetime.now().isoformat(), interaction.user.id, interaction.guild_id))
    db.commit()
    embed = Embed(title="💼 Work Complete!", description=f"You worked as a **{random.choice(jobs)}** and earned **{amount}** coins!", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="rob", description="🔫 Rob a member!")
async def rob(interaction: Interaction, member: Member = SlashOption(description="Member to rob", required=True)):
    if member == interaction.user:
        embed = Embed(title="❌ Error", description="You can't rob yourself!", color=0xED4245)
        embed.set_footer(text=BRANDING)
        await interaction.response.send_message(embed=embed)
        return
    
    economy = get_economy(interaction.user.id, interaction.guild_id)
    target_economy = get_economy(member.id, interaction.guild_id)
    
    if economy['rob_cooldown']:
        last_time = datetime.fromisoformat(economy['rob_cooldown'])
        if (datetime.now() - last_time).total_seconds() < 3600:
            remaining = 3600 - (datetime.now() - last_time).total_seconds()
            minutes = int(remaining // 60)
            embed = Embed(title="⏳ Cooldown", description=f"Wait **{minutes}** minutes!", color=0xFEE75C)
            embed.set_footer(text=BRANDING)
            await interaction.response.send_message(embed=embed)
            return
    
    if target_economy['coins'] < 10:
        embed = Embed(title="❌ Poor Target", description=f"{member.mention} doesn't have enough coins!", color=0xED4245)
        embed.set_footer(text=BRANDING)
        await interaction.response.send_message(embed=embed)
        return
    
    success = random.random() < 0.6
    if success:
        amount = random.randint(10, min(50, target_economy['coins']))
        remove_coins(member.id, interaction.guild_id, amount)
        add_coins(interaction.user.id, interaction.guild_id, amount)
        embed = Embed(title="✅ Robbery Successful!", description=f"You robbed **{amount}** coins from {member.mention}!", color=0x57F287)
    else:
        penalty = random.randint(5, 20)
        remove_coins(interaction.user.id, interaction.guild_id, penalty)
        embed = Embed(title="❌ Robbery Failed!", description=f"You got caught and lost **{penalty}** coins!", color=0xED4245)
    
    db.execute("UPDATE economy SET rob_cooldown = ? WHERE user_id = ? AND guild_id = ?", (datetime.now().isoformat(), interaction.user.id, interaction.guild_id))
    db.commit()
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="balance", description="💰 Check balance")
async def balance(interaction: Interaction, member: Member = SlashOption(description="Member", required=False)):
    if not member:
        member = interaction.user
    economy = get_economy(member.id, interaction.guild_id)
    embed = Embed(title=f"💰 {member.display_name}'s Balance", color=0x57F287)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="🪙 Coins", value=f"**{economy['coins']}**", inline=True)
    embed.add_field(name="🏦 Bank", value=f"**{economy['bank']}**", inline=True)
    embed.add_field(name="💎 Total", value=f"**{economy['coins'] + economy['bank']}**", inline=True)
    embed.set_footer(text=BRANDING)
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
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="shop", description="🛒 View shop")
async def shop(interaction: Interaction):
    items = db.fetchall("SELECT * FROM shop_items WHERE guild_id = ?", (interaction.guild_id,))
    if not items:
        embed = Embed(title="🛒 Shop", description="Shop is empty!", color=0x5865F2)
        embed.set_footer(text=BRANDING)
        return await interaction.response.send_message(embed=embed)
    embed = Embed(title=f"🛒 Shop - {interaction.guild.name}", color=0x5865F2)
    for item in items[:10]:
        embed.add_field(name=f"{item['emoji'] or '🛒'} {item['name']}", value=f"💰 {item['price']} coins\n{item['description']}", inline=False)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="add_shop_item", description="➕ Add shop item (Admin only)")
@commands.has_permissions(administrator=True)
async def add_shop_item(interaction: Interaction, name: str = SlashOption(description="Name", required=True), description: str = SlashOption(description="Description", required=True), price: int = SlashOption(description="Price", required=True), emoji: str = SlashOption(description="Emoji", required=False)):
    db.execute("INSERT INTO shop_items (guild_id, name, description, price, emoji) VALUES (?, ?, ?, ?, ?)",
               (interaction.guild_id, name, description, price, emoji or "🛒"))
    db.commit()
    embed = Embed(title="✅ Shop Item Added", description=f"Added **{name}** for {price} coins!", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# COUNTRY GAME
# =============================================================================

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
        self.answer = TextInput(label="What country is this flag from?", placeholder="Type the country name...", style=TextInputStyle.short, required=True)
        self.add_item(self.answer)
    
    async def callback(self, interaction: Interaction):
        user_answer = self.answer.value.strip().lower()
        correct_answer = self.country_data['name'].lower()
        
        if user_answer == correct_answer:
            score = db.fetchone("SELECT * FROM country_scores WHERE user_id = ? AND guild_id = ?", (interaction.user.id, interaction.guild_id))
            if not score:
                db.execute("INSERT INTO country_scores (user_id, guild_id, score, correct) VALUES (?, ?, 10, 1)", (interaction.user.id, interaction.guild_id))
            else:
                db.execute("UPDATE country_scores SET score = score + 10, correct = correct + 1 WHERE user_id = ? AND guild_id = ?", (interaction.user.id, interaction.guild_id))
            db.commit()
            embed = Embed(title="✅ Correct!", description=f"It's **{self.country_data['name']}**! You earned 10 points!", color=0x57F287)
            embed.set_footer(text=BRANDING)
            await interaction.response.send_message(embed=embed)
        else:
            db.execute("UPDATE country_scores SET wrong = wrong + 1 WHERE user_id = ? AND guild_id = ?", (interaction.user.id, interaction.guild_id))
            db.commit()
            embed = Embed(title="❌ Wrong!", description=f"It was **{self.country_data['name']}**!", color=0xED4245)
            embed.set_footer(text=BRANDING)
            await interaction.response.send_message(embed=embed)

@bot.slash_command(name="country", description="🌍 Play country guessing game!")
async def country(interaction: Interaction):
    country = random.choice(COUNTRIES)
    embed = Embed(title="🌍 Country Guess Game!", description=f"**{country['flag']}** Which country is this flag from?\n\nClick the button below to guess!", color=0x5865F2, timestamp=datetime.now())
    embed.set_footer(text=BRANDING)
    view = CountryGuessView(country)
    await interaction.response.send_message(embed=embed, view=view)

@bot.slash_command(name="country_score", description="🌍 Check country score")
async def country_score(interaction: Interaction, member: Member = SlashOption(description="Member", required=False)):
    if not member:
        member = interaction.user
    score = db.fetchone("SELECT * FROM country_scores WHERE user_id = ? AND guild_id = ?", (member.id, interaction.guild_id))
    if not score:
        embed = Embed(title="🌍 Country Score", description=f"{member.mention} hasn't played yet!", color=0x5865F2)
        embed.set_footer(text=BRANDING)
        return await interaction.response.send_message(embed=embed)
    embed = Embed(title=f"🌍 {member.display_name}'s Country Score", color=0x5865F2)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="⭐ Score", value=f"**{score['score']}**", inline=True)
    embed.add_field(name="✅ Correct", value=f"**{score['correct']}**", inline=True)
    embed.add_field(name="❌ Wrong", value=f"**{score['wrong']}**", inline=True)
    embed.set_footer(text=BRANDING)
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
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# FUN COMMANDS
# =============================================================================

@bot.slash_command(name="8ball", description="🎱 Ask the magic 8-ball!")
async def eight_ball(interaction: Interaction, question: str = SlashOption(description="Question", required=True)):
    responses = ["It is certain.", "It is decidedly so.", "Without a doubt.", "Yes - definitely.", "You may rely on it.", "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.", "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.", "Concentrate and ask again.", "Don't count on it.", "My reply is no.", "My sources say no.", "Outlook not so good.", "Very doubtful."]
    embed = Embed(title="🎱 8-Ball", description=f"Question: {question}\n\n**Answer:** {random.choice(responses)}", color=0x9B59B6)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="flip", description="🪙 Flip a coin!")
async def flip(interaction: Interaction):
    embed = Embed(title="🪙 Coin Flip", description=f"**{random.choice(['Heads', 'Tails'])}**!", color=0x5865F2)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="dice", description="🎲 Roll a dice!")
async def dice(interaction: Interaction, sides: int = SlashOption(description="Sides", min_value=2, max_value=100, required=False)):
    sides = sides or 6
    embed = Embed(title="🎲 Dice Roll", description=f"Rolled a **{random.randint(1, sides)}** on a {sides}-sided dice!", color=0x5865F2)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="joke", description="😂 Get a joke!")
async def joke(interaction: Interaction):
    jokes = ["Why don't scientists trust atoms? Because they make up everything!", "What do you call a fake noodle? An impasta!", "Why did the scarecrow win an award? He was outstanding in his field!", "Why don't eggs tell jokes? They'd crack each other up!"]
    embed = Embed(title="😂 Joke", description=random.choice(jokes), color=0x5865F2)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="roast", description="🔥 Roast a member!")
async def roast(interaction: Interaction, member: Member = SlashOption(description="Member", required=True)):
    roasts = [f"{member.mention}, you're not stupid; you just have bad luck thinking.", f"{member.mention}, you bring everyone so much joy... when you leave.", f"{member.mention}, you're like a cloud. When you disappear, it's a beautiful day."]
    embed = Embed(title="🔥 ROASTED!", description=random.choice(roasts), color=0xED4245)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="kiss", description="💋 Kiss a member!")
async def kiss(interaction: Interaction, member: Member = SlashOption(description="Member", required=True)):
    if member == interaction.user:
        embed = Embed(title="💋", description="You kissed yourself! That's sad...", color=0x5865F2)
        embed.set_footer(text=BRANDING)
        await interaction.response.send_message(embed=embed)
        return
    embed = Embed(title="💋 Kiss!", description=f"{interaction.user.mention} kissed {member.mention}! 😘", color=0xFF6B81)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="hug", description="🤗 Hug a member!")
async def hug(interaction: Interaction, member: Member = SlashOption(description="Member", required=True)):
    if member == interaction.user:
        embed = Embed(title="🤗", description="You hugged yourself! You need friends.", color=0x5865F2)
        embed.set_footer(text=BRANDING)
        await interaction.response.send_message(embed=embed)
        return
    embed = Embed(title="🤗 Hug!", description=f"{interaction.user.mention} hugged {member.mention}! 🫂", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="pat", description="👋 Pat a member!")
async def pat(interaction: Interaction, member: Member = SlashOption(description="Member", required=True)):
    embed = Embed(title="👋 Pat!", description=f"{interaction.user.mention} patted {member.mention} on the head! 👋", color=0x5865F2)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

# =============================================================================
# UTILITY COMMANDS
# =============================================================================

@bot.slash_command(name="ping", description="🏓 Check bot latency!")
async def ping(interaction: Interaction):
    embed = Embed(title="🏓 Pong!", description=f"Latency: **{round(bot.latency * 1000)}ms**", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="help", description="📖 Show all commands!")
async def help_command(interaction: Interaction):
    embed = Embed(title="📖 Commands", color=0x5865F2, timestamp=datetime.now())
    embed.add_field(name="👑 Group Management", value="/group_add_manager, /group_remove_manager, /group_add_admin, /group_remove_admin, /group_list", inline=False)
    embed.add_field(name="🔄 Server Sync", value="/sync_server, /list_servers, /sync_list, /rank_user", inline=False)
    embed.add_field(name="🌍 Global", value="/global_ban, /global_unban, /global_kick, /global_announce, /global_dm", inline=False)
    embed.add_field(name="🎫 Tickets", value="/ticket_panel_custom, /ticket_panel, /ticket_setup, /ticket_close", inline=False)
    embed.add_field(name="🎁 Giveaways", value="/giveaway_start, /giveaway_end", inline=False)
    embed.add_field(name="🛡️ Admin", value="/add_admin, /remove_admin, /admins, /ban, /kick, /clear, /warn, /warnings, /mute, /audit", inline=False)
    embed.add_field(name="💰 Economy", value="/daily, /work, /rob, /balance, /shop, /add_shop_item, /leaderboard_economy", inline=False)
    embed.add_field(name="🌍 Country Game", value="/country, /country_score, /country_leaderboard", inline=False)
    embed.add_field(name="🎮 Fun", value="/8ball, /flip, /dice, /joke, /roast, /kiss, /hug, /pat", inline=False)
    embed.add_field(name="📊 Utility", value="/ping, /server, /rank, /leaderboard, /setup, /announce, /event_create, /events, /restart, /bot_stats, /backup, /restore, /recovery_code", inline=False)
    embed.set_footer(text=f"{BRANDING} • v{VERSION} • {len(bot.guilds)} servers")
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
    embed.set_footer(text=f"{BRANDING} • ID: {guild.id}")
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="rank", description="🎯 Check your level")
async def rank(interaction: Interaction, member: Member = SlashOption(description="Member", required=False)):
    if not member:
        member = interaction.user
    data = get_member(member.id, interaction.guild_id)
    embed = Embed(title=f"👤 {member.display_name}'s Profile", color=member.color.value if member.color else 0x5865F2)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="📊 Level", value=f"**{data['level']}**", inline=True)
    embed.add_field(name="⭐ XP", value=f"**{data['xp']}**", inline=True)
    embed.add_field(name="💬 Messages", value=f"**{data['messages']}**", inline=True)
    embed.add_field(name="⚠️ Warnings", value=f"**{data['warnings']}**", inline=True)
    embed.set_footer(text=BRANDING)
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
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="setup", description="⚙️ Setup bot (Admin only)")
@commands.has_permissions(administrator=True)
async def setup(interaction: Interaction, type: str = SlashOption(description="Type", choices={"welcome": "welcome", "mod_log": "mod_log", "level": "level", "announcement": "announcement"}, required=True), channel: TextChannel = SlashOption(description="Channel", required=True)):
    db.execute(f"UPDATE guilds SET {type}_channel = ? WHERE id = ?", (channel.id, interaction.guild_id))
    db.commit()
    embed = Embed(title="✅ Setup Complete", description=f"{type.capitalize()} channel set to {channel.mention}", color=0x57F287)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="announce", description="📢 Create announcement (Admin only)")
@commands.has_permissions(administrator=True)
async def announce(interaction: Interaction, title: str = SlashOption(description="Title", required=True), content: str = SlashOption(description="Content", required=True), image_url: str = SlashOption(description="Image URL", required=False)):
    embed = Embed(title=f"📢 {title}", description=content, color=0xF1C40F, timestamp=datetime.now())
    embed.set_footer(text=BRANDING)
    if image_url:
        embed.set_image(url=image_url)
    guild_data = get_guild(interaction.guild_id)
    channel_id = guild_data["announcement_channel"]
    if channel_id:
        channel = bot.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)
            embed = Embed(title="✅ Sent", description=f"Announcement sent to {channel.mention}", color=0x57F287)
            embed.set_footer(text=BRANDING)
            await interaction.response.send_message(embed=embed)
            return
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="event_create", description="🎪 Create event (Admin only)")
@commands.has_permissions(administrator=True)
async def event_create(interaction: Interaction, title: str = SlashOption(description="Title", required=True), description: str = SlashOption(description="Description", required=True), location: str = SlashOption(description="Location", required=True), max_participants: int = SlashOption(description="Max participants", required=False)):
    db.execute("INSERT INTO events (guild_id, title, description, location, start_time, organizer_id, max_participants, participants, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
               (interaction.guild_id, title, description, location, datetime.now().isoformat(), interaction.user.id, max_participants or 0, json.dumps([]), datetime.now().isoformat()))
    db.commit()
    embed = Embed(title="🎪 Event Created", description=f"**{title}**\n{description}\n📍 {location}", color=0x1ABC9C)
    embed.set_footer(text=BRANDING)
    await interaction.response.send_message(embed=embed)

@bot.slash_command(name="events", description="📋 List upcoming events")
async def events(interaction: Interaction):
    events = db.fetchall("SELECT * FROM events WHERE guild_id = ? AND status = 'upcoming' ORDER BY start_time LIMIT 10", (interaction.guild_id,))
    if not events:
        embed = Embed(title="📋 No Events", description="No upcoming events", color=0x5865F2)
        embed.set_footer(text=BRANDING)
        return await interaction.response.send_message(embed=embed)
    embed = Embed(title=f"📋 Upcoming Events - {interaction.guild.name}", color=0x1ABC9C)
    for event in events:
        organizer = interaction.guild.get_member(event['organizer_id'])
        embed.add_field(name=event['title'], value=f"📍 {event['location']}\n👤 {organizer.mention if organizer else 'Unknown'}", inline=False)
    embed.set_footer(text=BRANDING)
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
    <head><title>🇷🇴 Romanian Oversight Bot</title>
    <style>
        body {{ margin:0; padding:0; font-family:'Segoe UI',sans-serif; background:linear-gradient(135deg,#667eea 0%,#764ba2 100%); color:white; display:flex; justify-content:center; align-items:center; min-height:100vh; }}
        .container {{ text-align:center; padding:40px; background:rgba(255,255,255,0.1); border-radius:20px; backdrop-filter:blur(10px); max-width:600px; }}
        h1 {{ font-size:2.5em; }}
        .status {{ padding:15px; background:rgba(0,255,0,0.2); border-radius:10px; display:inline-block; }}
        .stat {{ display:inline-block; margin:0 10px; padding:10px 20px; background:rgba(255,255,255,0.1); border-radius:10px; }}
        .footer {{ margin-top:30px; opacity:0.7; }}
    </style>
    </head>
    <body>
        <div class="container">
            <h1>🇷🇴 Romanian Oversight Bot</h1>
            <p>Enterprise Grade - v{VERSION}</p>
            <div class="status">✅ Bot is ONLINE</div>
            <div style="margin:20px 0;">
                <div class="stat">🎯 {len(bot.guilds)} Servers</div>
                <div class="stat">👥 {sum(g.member_count for g in bot.guilds)} Users</div>
                <div class="stat">🔑 {recovery.recovery_code}</div>
                <div class="stat">👑 Alpha: TommyTactical</div>
            </div>
            <div class="footer">{BRANDING}</div>
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
        "uptime": str(datetime.now() - START_TIME),
        "recovery_code": recovery.recovery_code,
        "alpha": "TommyTactical (922061012486725632)",
        "branding": BRANDING
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
        embed = Embed(title="❌ Permission Denied", description="You need higher permissions!", color=0xED4245)
        embed.set_footer(text=BRANDING)
        await interaction.response.send_message(embed=embed, ephemeral=True)
    else:
        embed = Embed(title="❌ Error", description=str(error), color=0xED4245)
        embed.set_footer(text=BRANDING)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# =============================================================================
# MAIN
# =============================================================================

def signal_handler(sig, frame):
    print("🛑 Shutting down...")
    recovery.create_backup()
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    thread = Thread(target=run_web, daemon=True)
    thread.start()
    bot.run(TOKEN)
