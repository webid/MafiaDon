import discord
import os
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

# Configuration
PLAYER_ROLE_NAME = os.getenv('PLAYER_ROLE_NAME', 'i play mafia')
ALLOWED_CATEGORY_ID = os.getenv('ALLOWED_CATEGORY_ID')

# Shared Game State
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
