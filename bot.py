import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio
from typing import Optional
from collections import defaultdict

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = os.getenv('GUILD_ID')

# Configuration - The role name that identifies mafia players
PLAYER_ROLE_NAME = os.getenv('PLAYER_ROLE_NAME', 'i play mafia')

# Optional: Limit bot to specific category (set in .env or leave empty for all categories)
ALLOWED_CATEGORY_ID = os.getenv('ALLOWED_CATEGORY_ID')

# Bot setup with required intents
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)


def get_player_role(guild: discord.Guild) -> Optional[discord.Role]:
    """Get the mafia player role from the guild."""
    for role in guild.roles:
        if role.name.lower() == PLAYER_ROLE_NAME.lower():
            return role
    return None


def is_in_allowed_category(channel: discord.abc.GuildChannel) -> bool:
    """Check if the channel is in an allowed category."""
    if not ALLOWED_CATEGORY_ID:
        return True  # No restriction if not configured
    
    if hasattr(channel, 'category_id') and channel.category_id:
        return str(channel.category_id) == ALLOWED_CATEGORY_ID
    return False


def has_player_role(member: discord.Member) -> bool:
    """Check if a member has the mafia player role."""
    role = get_player_role(member.guild)
    if role:
        return role in member.roles
    return False


def get_players_with_role(guild: discord.Guild) -> list[discord.Member]:
    """Get all members with the mafia player role."""
    role = get_player_role(guild)
    if role:
        return [m for m in role.members if not m.bot]
    return []


class GameState:
    """Tracks the state of a Mafia game in a specific channel."""
    
    def __init__(self):
        self.votes: dict[int, int] = {}  # voter_id -> target_id
        self.hammer_active: bool = False
        self.hammer_end_time: Optional[datetime] = None
        self.game_channel: Optional[discord.TextChannel] = None
        self.last_update_time: Optional[datetime] = None
        self.eliminated_players: set[int] = set()  # Players who have been eliminated
        self.game_active: bool = False
    
    def get_active_players(self, guild: discord.Guild) -> list[discord.Member]:
        """Get all active players (have role and not eliminated)."""
        all_players = get_players_with_role(guild)
        return [p for p in all_players if p.id not in self.eliminated_players]
    
    def eliminate_player(self, member: discord.Member):
        """Mark a player as eliminated."""
        self.eliminated_players.add(member.id)
        # Remove any votes to/from this player
        self.votes = {k: v for k, v in self.votes.items() 
                     if k != member.id and v != member.id}
    
    def cast_vote(self, voter_id: int, target_id: int) -> bool:
        """Cast a vote. Returns True if successful."""
        self.votes[voter_id] = target_id
        return True
    
    def remove_vote(self, voter_id: int) -> bool:
        """Remove a vote. Returns True if a vote was removed."""
        if voter_id in self.votes:
            del self.votes[voter_id]
            return True
        return False
    
    def get_vote_tally(self) -> dict[int, list[int]]:
        """Get current vote tally. Returns {target_id: [voter_ids]}"""
        tally = defaultdict(list)
        for voter_id, target_id in self.votes.items():
            tally[target_id].append(voter_id)
        return dict(tally)
    
    def get_majority_threshold(self, guild: discord.Guild) -> int:
        """Get the number of votes needed for majority."""
        active_players = self.get_active_players(guild)
        return (len(active_players) // 2) + 1
    
    def check_majority(self, guild: discord.Guild) -> Optional[int]:
        """Check if any player has majority votes. Returns player_id or None."""
        threshold = self.get_majority_threshold(guild)
        tally = self.get_vote_tally()
        for target_id, voters in tally.items():
            if len(voters) >= threshold:
                return target_id
        return None
    
    def start_hammer(self, channel: discord.TextChannel):
        """Start the 24-hour hammer countdown."""
        self.hammer_active = True
        self.hammer_end_time = datetime.now() + timedelta(hours=24)
        self.game_channel = channel
        self.last_update_time = datetime.now()
    
    def get_time_remaining(self) -> Optional[timedelta]:
        """Get time remaining in hammer countdown."""
        if not self.hammer_active or not self.hammer_end_time:
            return None
        remaining = self.hammer_end_time - datetime.now()
        if remaining.total_seconds() < 0:
            return timedelta(0)
        return remaining
    
    def is_hammer_expired(self) -> bool:
        """Check if the hammer countdown has expired."""
        remaining = self.get_time_remaining()
        return remaining is not None and remaining.total_seconds() <= 0


# Store game states per guild
games: dict[int, GameState] = {}


def get_game(guild_id: int) -> GameState:
    """Get or create a game state for a guild."""
    if guild_id not in games:
        games[guild_id] = GameState()
    return games[guild_id]


def format_tally(game: GameState, guild: discord.Guild) -> str:
    """Format the current vote tally as a string."""
    active_players = game.get_active_players(guild)
    tally = game.get_vote_tally()
    
    if not tally:
        return "📊 **Vote Tally**\n\nNo votes cast yet."
    
    lines = ["📊 **Vote Tally**\n"]
    threshold = game.get_majority_threshold(guild)
    lines.append(f"*Majority to hammer: {threshold} votes (of {len(active_players)} players)*\n")
    
    # Sort by vote count descending
    sorted_tally = sorted(tally.items(), key=lambda x: len(x[1]), reverse=True)
    
    for target_id, voter_ids in sorted_tally:
        target = guild.get_member(target_id)
        target_name = target.display_name if target else f"Unknown ({target_id})"
        vote_count = len(voter_ids)
        
        # Get voter names
        voter_names = []
        for vid in voter_ids:
            voter = guild.get_member(vid)
            voter_names.append(voter.display_name if voter else f"Unknown")
        
        voters_str = ", ".join(voter_names)
        lines.append(f"**{target_name}** ({vote_count}): {voters_str}")
    
    # Show players with no votes
    players_with_votes = set(tally.keys())
    no_votes = [p for p in active_players if p.id not in players_with_votes]
    if no_votes:
        no_vote_names = ", ".join(p.display_name for p in no_votes)
        lines.append(f"\n*No votes: {no_vote_names}*")
    
    return "\n".join(lines)


def format_time_remaining(td: timedelta) -> str:
    """Format a timedelta as a human-readable string."""
    total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{hours}h {minutes}m"
    elif minutes > 0:
        return f"{minutes}m {seconds}s"
    else:
        return f"{seconds}s"


class PlayerSelect(discord.ui.Select):
    """Dropdown menu for selecting a player to vote for."""
    
    def __init__(self, game: GameState, voter: discord.Member, guild: discord.Guild):
        self.game = game
        self.voter = voter
        
        active_players = game.get_active_players(guild)
        
        options = []
        for player in active_players:
            if player.id != voter.id:  # Can't vote for yourself
                options.append(discord.SelectOption(
                    label=player.display_name,
                    value=str(player.id),
                    description=f"Vote for {player.display_name}"
                ))
        
        if not options:
            options = [discord.SelectOption(label="No players available", value="none")]
        
        super().__init__(
            placeholder="Select a player to vote for...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        if self.values[0] == "none":
            await interaction.response.send_message("No valid players to vote for!", ephemeral=True)
            return
        
        target_id = int(self.values[0])
        target = interaction.guild.get_member(target_id)
        
        if not target:
            await interaction.response.send_message("Player not found!", ephemeral=True)
            return
        
        # Verify target still has the player role
        if not has_player_role(target):
            await interaction.response.send_message(
                f"{target.display_name} no longer has the **{PLAYER_ROLE_NAME}** role!",
                ephemeral=True
            )
            return
        
        # Cast the vote
        self.game.cast_vote(self.voter.id, target.id)
        tally = format_tally(self.game, interaction.guild)
        
        # Check for majority
        majority_player_id = self.game.check_majority(interaction.guild)
        
        if majority_player_id and not self.game.hammer_active:
            majority_player = interaction.guild.get_member(majority_player_id)
            self.game.start_hammer(interaction.channel)
            
            await interaction.response.send_message(
                f"🗳️ **{self.voter.display_name}** voted for **{target.display_name}**\n\n"
                f"{tally}\n\n"
                f"⚠️ **MAJORITY REACHED!** {majority_player.display_name if majority_player else 'Unknown'} "
                f"has been hammered!\n"
                f"🔨 **24-hour countdown started!** Final tally in {format_time_remaining(self.game.get_time_remaining())}.\n"
                f"*Updates will be posted every 4 hours.*"
            )
        else:
            hammer_info = ""
            if self.game.hammer_active:
                remaining = self.game.get_time_remaining()
                hammer_info = f"\n\n🔨 *Hammer active! Time remaining: {format_time_remaining(remaining)}*"
            
            await interaction.response.send_message(
                f"🗳️ **{self.voter.display_name}** voted for **{target.display_name}**\n\n"
                f"{tally}{hammer_info}"
            )


class VoteView(discord.ui.View):
    """View containing the player selection dropdown."""
    
    def __init__(self, game: GameState, voter: discord.Member, guild: discord.Guild):
        super().__init__(timeout=60)
        self.add_item(PlayerSelect(game, voter, guild))


# Slash Commands
@bot.tree.command(name="vote", description="Vote for a player in the Mafia game")
async def vote(interaction: discord.Interaction):
    """Open a dropdown to vote for a player."""
    # Check if in allowed category
    if not is_in_allowed_category(interaction.channel):
        await interaction.response.send_message(
            "❌ This command can only be used in the Mafia game channels!",
            ephemeral=True
        )
        return
    
    game = get_game(interaction.guild.id)
    
    if not game.game_active:
        await interaction.response.send_message(
            "❌ No game in progress! Use `/startgame` to begin.",
            ephemeral=True
        )
        return
    
    voter = interaction.user
    
    # Check if voter has the player role
    if not has_player_role(voter):
        await interaction.response.send_message(
            f"❌ You don't have the **{PLAYER_ROLE_NAME}** role!",
            ephemeral=True
        )
        return
    
    # Check if voter is eliminated
    if voter.id in game.eliminated_players:
        await interaction.response.send_message(
            "❌ You have been eliminated and cannot vote!",
            ephemeral=True
        )
        return
    
    view = VoteView(game, voter, interaction.guild)
    await interaction.response.send_message(
        "Select a player to vote for:",
        view=view,
        ephemeral=True
    )


@bot.tree.command(name="unvote", description="Remove your current vote")
async def unvote(interaction: discord.Interaction):
    """Remove the user's current vote."""
    # Check if in allowed category
    if not is_in_allowed_category(interaction.channel):
        await interaction.response.send_message(
            "❌ This command can only be used in the Mafia game channels!",
            ephemeral=True
        )
        return
    
    game = get_game(interaction.guild.id)
    
    if not game.game_active:
        await interaction.response.send_message(
            "❌ No game in progress!",
            ephemeral=True
        )
        return
    
    voter = interaction.user
    
    # Check if voter has the player role
    if not has_player_role(voter):
        await interaction.response.send_message(
            f"❌ You don't have the **{PLAYER_ROLE_NAME}** role!",
            ephemeral=True
        )
        return
    
    if game.remove_vote(voter.id):
        tally = format_tally(game, interaction.guild)
        hammer_info = ""
        if game.hammer_active:
            remaining = game.get_time_remaining()
            hammer_info = f"\n\n🔨 *Hammer active! Time remaining: {format_time_remaining(remaining)}*"
        
        await interaction.response.send_message(
            f"🗳️ **{voter.display_name}** removed their vote.\n\n{tally}{hammer_info}"
        )
    else:
        await interaction.response.send_message(
            "You don't have an active vote to remove.",
            ephemeral=True
        )


@bot.tree.command(name="hammer", description="Manually trigger the 24-hour hammer countdown")
async def hammer(interaction: discord.Interaction):
    """Manually start the hammer countdown."""
    # Check if in allowed category
    if not is_in_allowed_category(interaction.channel):
        await interaction.response.send_message(
            "❌ This command can only be used in the Mafia game channels!",
            ephemeral=True
        )
        return
    
    game = get_game(interaction.guild.id)
    
    if not game.game_active:
        await interaction.response.send_message(
            "❌ No game in progress!",
            ephemeral=True
        )
        return
    
    if game.hammer_active:
        remaining = game.get_time_remaining()
        await interaction.response.send_message(
            f"🔨 Hammer is already active! Time remaining: {format_time_remaining(remaining)}",
            ephemeral=True
        )
        return
    
    game.start_hammer(interaction.channel)
    tally = format_tally(game, interaction.guild)
    
    await interaction.response.send_message(
        f"🔨 **HAMMER ACTIVATED!**\n\n"
        f"24-hour countdown started! Final tally will be posted in {format_time_remaining(game.get_time_remaining())}.\n"
        f"*Updates will be posted every 4 hours.*\n\n"
        f"{tally}"
    )


@bot.tree.command(name="tally", description="Show the current vote tally")
async def tally(interaction: discord.Interaction):
    """Display the current vote tally."""
    # Check if in allowed category
    if not is_in_allowed_category(interaction.channel):
        await interaction.response.send_message(
            "❌ This command can only be used in the Mafia game channels!",
            ephemeral=True
        )
        return
    
    game = get_game(interaction.guild.id)
    
    if not game.game_active:
        await interaction.response.send_message(
            "❌ No game in progress!",
            ephemeral=True
        )
        return
    
    tally_str = format_tally(game, interaction.guild)
    hammer_info = ""
    if game.hammer_active:
        remaining = game.get_time_remaining()
        hammer_info = f"\n\n🔨 *Hammer active! Time remaining: {format_time_remaining(remaining)}*"
    
    await interaction.response.send_message(f"{tally_str}{hammer_info}")


@bot.tree.command(name="startgame", description="Start a new Mafia game with players who have the player role")
async def startgame(interaction: discord.Interaction):
    """Start a new game, automatically detecting players with the mafia role."""
    # Check if in allowed category
    if not is_in_allowed_category(interaction.channel):
        await interaction.response.send_message(
            "❌ This command can only be used in the Mafia game channels!",
            ephemeral=True
        )
        return

    # Check permissions
    if not is_manager_or_mod(interaction):
        await interaction.response.send_message(
            "❌ You do not have permission to use this command! (Managers/Mods only)",
            ephemeral=True
        )
        return
    
    game = get_game(interaction.guild.id)
    
    # Check for player role
    role = get_player_role(interaction.guild)
    if not role:
        await interaction.response.send_message(
            f"❌ Could not find a role named **{PLAYER_ROLE_NAME}**!\n"
            f"Please create this role and assign it to players.",
            ephemeral=True
        )
        return
    
    # Get all players with the role
    players = get_players_with_role(interaction.guild)
    
    if len(players) < 3:
        await interaction.response.send_message(
            f"❌ Not enough players! Found {len(players)} with the **{PLAYER_ROLE_NAME}** role.\n"
            f"Need at least 3 players to start a game.",
            ephemeral=True
        )
        return
    
    # Reset game state
    games[interaction.guild.id] = GameState()
    game = games[interaction.guild.id]
    game.game_active = True
    game.game_channel = interaction.channel
    
    player_list = "\n".join(f"• {p.display_name}" for p in players)
    
    await interaction.response.send_message(
        f"🎮 **MAFIA GAME STARTED!**\n\n"
        f"👥 **Players ({len(players)}):**\n{player_list}\n\n"
        f"*Majority to hammer: {game.get_majority_threshold(interaction.guild)} votes*\n\n"
        f"Use `/vote` to vote for a player!\n"
        f"Use `/unvote` to remove your vote.\n"
        f"Use `/tally` to see the current standings."
    )


@bot.tree.command(name="players", description="Show all players in the current game")
async def players(interaction: discord.Interaction):
    """List all players with the mafia player role."""
    # Check if in allowed category
    if not is_in_allowed_category(interaction.channel):
        await interaction.response.send_message(
            "❌ This command can only be used in the Mafia game channels!",
            ephemeral=True
        )
        return
    
    game = get_game(interaction.guild.id)
    
    role = get_player_role(interaction.guild)
    if not role:
        await interaction.response.send_message(
            f"❌ Could not find a role named **{PLAYER_ROLE_NAME}**!",
            ephemeral=True
        )
        return
    
    all_players = get_players_with_role(interaction.guild)
    active_players = game.get_active_players(interaction.guild)
    eliminated = [p for p in all_players if p.id in game.eliminated_players]
    
    if not all_players:
        await interaction.response.send_message(
            f"No players with the **{PLAYER_ROLE_NAME}** role found.",
            ephemeral=True
        )
        return
    
    active_list = "\n".join(f"• {p.display_name}" for p in active_players) if active_players else "None"
    eliminated_list = "\n".join(f"• ~~{p.display_name}~~" for p in eliminated) if eliminated else ""
    
    message = f"👥 **Active Players ({len(active_players)})**\n{active_list}"
    
    if eliminated_list:
        message += f"\n\n💀 **Eliminated:**\n{eliminated_list}"
    
    if game.game_active:
        message += f"\n\n*Majority threshold: {game.get_majority_threshold(interaction.guild)} votes*"
    else:
        message += f"\n\n*Game not started. Use `/startgame` to begin.*"
    
    await interaction.response.send_message(message)



def is_manager_or_mod(interaction: discord.Interaction) -> bool:
    """Check if the user has manager or moderator permissions."""
    if not isinstance(interaction.user, discord.Member):
        return False
    
    # Check for direct administrator permission
    if interaction.user.guild_permissions.administrator:
        return True
        
    # Check for other mod-like permissions
    perms = interaction.user.guild_permissions
    return (perms.manage_guild or 
            perms.kick_members or 
            perms.ban_members or 
            perms.manage_roles)


@bot.tree.command(name="eliminate", description="Mark a player as eliminated (moderator only)")
@app_commands.describe(player="The player to eliminate")
async def eliminate(interaction: discord.Interaction, player: discord.Member):
    """Mark a player as eliminated from the game."""
    # Check if in allowed category
    if not is_in_allowed_category(interaction.channel):
        await interaction.response.send_message(
            "❌ This command can only be used in the Mafia game channels!",
            ephemeral=True
        )
        return
        
    # Check permissions
    if not is_manager_or_mod(interaction):
        await interaction.response.send_message(
            "❌ You do not have permission to use this command! (Managers/Mods only)",
            ephemeral=True
        )
        return
    
    game = get_game(interaction.guild.id)
    
    if not has_player_role(player):
        await interaction.response.send_message(
            f"❌ {player.display_name} doesn't have the **{PLAYER_ROLE_NAME}** role!",
            ephemeral=True
        )
        return
    
    if player.id in game.eliminated_players:
        await interaction.response.send_message(
            f"❌ {player.display_name} is already eliminated!",
            ephemeral=True
        )
        return
    
    game.eliminate_player(player)
    active_players = game.get_active_players(interaction.guild)
    
    await interaction.response.send_message(
        f"💀 **{player.display_name}** has been eliminated!\n\n"
        f"*Remaining players: {len(active_players)}*\n"
        f"*New majority threshold: {game.get_majority_threshold(interaction.guild)} votes*"
    )


@bot.tree.command(name="resetgame", description="Reset the current game (clears all votes and eliminations)")
async def resetgame(interaction: discord.Interaction):
    """Reset the current game."""
    # Check if in allowed category
    if not is_in_allowed_category(interaction.channel):
        await interaction.response.send_message(
            "❌ This command can only be used in the Mafia game channels!",
            ephemeral=True
        )
        return

    # Check permissions
    if not is_manager_or_mod(interaction):
        await interaction.response.send_message(
            "❌ You do not have permission to use this command! (Managers/Mods only)",
            ephemeral=True
        )
        return
    
    games[interaction.guild.id] = GameState()
    
    await interaction.response.send_message(
        "🔄 Game has been reset! All votes and eliminations cleared.\n"
        "Use `/startgame` to begin a new game."
    )


@bot.tree.command(name="resetvotes", description="Reset all votes but keep game state")
async def resetvotes(interaction: discord.Interaction):
    """Reset votes but keep eliminations."""
    # Check if in allowed category
    if not is_in_allowed_category(interaction.channel):
        await interaction.response.send_message(
            "❌ This command can only be used in the Mafia game channels!",
            ephemeral=True
        )
        return
    
    game = get_game(interaction.guild.id)
    game.votes.clear()
    game.hammer_active = False
    game.hammer_end_time = None
    game.last_update_time = None
    
    active_players = game.get_active_players(interaction.guild)
    player_list = ", ".join(p.display_name for p in active_players)
    
    await interaction.response.send_message(
        f"🔄 All votes have been reset!\n\n"
        f"**Active players ({len(active_players)}):** {player_list}\n"
        f"*Majority threshold: {game.get_majority_threshold(interaction.guild)} votes*"
    )


@bot.tree.command(name="setrole", description="Set the player role name (default: 'i play mafia')")
@app_commands.describe(role_name="The name of the role that identifies mafia players")
async def setrole(interaction: discord.Interaction, role_name: str):
    """Change the player role name."""
    # Check permissions
    if not is_manager_or_mod(interaction):
        await interaction.response.send_message(
            "❌ You do not have permission to use this command! (Managers/Mods only)",
            ephemeral=True
        )
        return

    global PLAYER_ROLE_NAME
    
    # Check if the role exists
    role_found = None
    for role in interaction.guild.roles:
        if role.name.lower() == role_name.lower():
            role_found = role
            break
    
    if not role_found:
        await interaction.response.send_message(
            f"⚠️ Warning: No role named **{role_name}** found in this server.\n"
            f"Role name set anyway. Make sure to create this role!",
            ephemeral=True
        )
    else:
        PLAYER_ROLE_NAME = role_name
        players = get_players_with_role(interaction.guild)
        await interaction.response.send_message(
            f"✅ Player role set to **{role_name}**!\n"
            f"Found {len(players)} players with this role."
        )


@bot.tree.command(name="status", description="Show bot status and configuration")
async def status(interaction: discord.Interaction):
    """Show current bot configuration and game status."""
    game = get_game(interaction.guild.id)
    role = get_player_role(interaction.guild)
    
    role_status = f"✅ **{role.name}** ({len(role.members)} members)" if role else f"❌ Role '{PLAYER_ROLE_NAME}' not found"
    
    category_status = "All channels"
    if ALLOWED_CATEGORY_ID:
        category = interaction.guild.get_channel(int(ALLOWED_CATEGORY_ID))
        category_status = f"**{category.name}**" if category else f"Category ID: {ALLOWED_CATEGORY_ID}"
    
    game_status = "🎮 Active" if game.game_active else "⏸️ Not started"
    hammer_status = f"🔨 Active ({format_time_remaining(game.get_time_remaining())} remaining)" if game.hammer_active else "⏸️ Not active"
    
    await interaction.response.send_message(
        f"**MafiaDon Bot Status**\n\n"
        f"**Player Role:** {role_status}\n"
        f"**Allowed Category:** {category_status}\n"
        f"**Game Status:** {game_status}\n"
        f"**Hammer:** {hammer_status}\n\n"
        f"*Use `/startgame` to begin a new game.*"
    )


# Background task to check hammer countdowns and post updates
@tasks.loop(minutes=1)
async def check_hammer_countdown():
    """Check all games for hammer countdown updates and expiration."""
    for guild_id, game in games.items():
        if not game.hammer_active or not game.game_channel:
            continue
        
        now = datetime.now()
        remaining = game.get_time_remaining()
        
        if remaining is None:
            continue
        
        # Check if expired
        if game.is_hammer_expired():
            game.hammer_active = False
            guild = bot.get_guild(guild_id)
            if guild:
                tally = format_tally(game, guild)
                
                # Find who was hammered (player with most votes)
                vote_tally = game.get_vote_tally()
                if vote_tally:
                    hammered_id = max(vote_tally.keys(), key=lambda k: len(vote_tally[k]))
                    hammered = guild.get_member(hammered_id)
                    hammered_name = hammered.display_name if hammered else "Unknown"
                    
                    # Auto-eliminate the hammered player
                    if hammered:
                        game.eliminate_player(hammered)
                else:
                    hammered_name = "No one (no votes)"
                
                await game.game_channel.send(
                    f"⏰ **TIME'S UP!**\n\n"
                    f"🔨 **{hammered_name}** has been eliminated!\n\n"
                    f"**Final Tally:**\n{tally}"
                )
            continue
        
        # Check if we should post an update (every 4 hours)
        if game.last_update_time:
            time_since_update = now - game.last_update_time
            if time_since_update >= timedelta(hours=4):
                game.last_update_time = now
                guild = bot.get_guild(guild_id)
                if guild:
                    tally = format_tally(game, guild)
                    await game.game_channel.send(
                        f"⏰ **Hammer Update**\n\n"
                        f"Time remaining: **{format_time_remaining(remaining)}**\n\n"
                        f"{tally}"
                    )


@bot.event
async def on_ready():
    """Called when the bot is ready."""
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} guild(s)')
    print(f'Player role: {PLAYER_ROLE_NAME}')
    if ALLOWED_CATEGORY_ID:
        print(f'Restricted to category ID: {ALLOWED_CATEGORY_ID}')
    else:
        print('No category restriction (bot works in all channels)')
    
    # Sync slash commands
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f'Synced commands to guild {GUILD_ID}')
    else:
        await bot.tree.sync()
        print('Synced commands globally')
    
    # Start the background task
    if not check_hammer_countdown.is_running():
        check_hammer_countdown.start()


if __name__ == '__main__':
    if not TOKEN:
        print("ERROR: DISCORD_TOKEN not found in environment variables!")
        print("Create a .env file with:")
        print("  DISCORD_TOKEN=your_bot_token_here")
        print("  GUILD_ID=your_guild_id_here (optional, for faster command sync)")
        print("  PLAYER_ROLE_NAME=i play mafia (optional, default is 'i play mafia')")
        print("  ALLOWED_CATEGORY_ID=123456789 (optional, restricts bot to specific category)")
        exit(1)
    
    bot.run(TOKEN)
