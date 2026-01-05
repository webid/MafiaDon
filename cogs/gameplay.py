import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from utils import (
    get_game, is_in_allowed_category, has_player_role,
    get_players_with_role, format_tally, format_time_remaining,
    VoteView, games, PLAYER_ROLE_NAME, ALLOWED_CATEGORY_ID
)

class GameplayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_hammer_countdown.start()

    def cog_unload(self):
        self.check_hammer_countdown.cancel()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Global check for all commands in this Cog."""
        if not is_in_allowed_category(interaction.channel):
            await interaction.response.send_message(
                "❌ This command can only be used in the Mafia game channels!",
                ephemeral=True
            )
            return False
        return True

    @app_commands.command(name="vote", description="Vote for a player in the Mafia game")
    async def vote(self, interaction: discord.Interaction):
        """Open a dropdown to vote for a player."""
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

    @app_commands.command(name="unvote", description="Remove your current vote")
    async def unvote(self, interaction: discord.Interaction):
        """Remove the user's current vote."""
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

    @app_commands.command(name="hammer", description="Manually trigger the 24-hour hammer countdown")
    async def hammer(self, interaction: discord.Interaction):
        """Manually start the hammer countdown."""
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

    @app_commands.command(name="tally", description="Show the current vote tally")
    async def tally(self, interaction: discord.Interaction):
        """Display the current vote tally."""
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

    @app_commands.command(name="players", description="Show all players in the current game")
    async def players(self, interaction: discord.Interaction):
        """List all players with the mafia player role."""
        game = get_game(interaction.guild.id)
        
        # Note: Importing logic to reuse code - or just replicate it since it accesses globals not in class
        # But get_player_role is in utils.
        from utils import get_player_role
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

    @app_commands.command(name="status", description="Show bot status and configuration")
    async def status(self, interaction: discord.Interaction):
        """Show current bot configuration and game status."""
        game = get_game(interaction.guild.id)
        from utils import get_player_role
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
    
    @tasks.loop(minutes=1)
    async def check_hammer_countdown(self):
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
                guild = self.bot.get_guild(guild_id)
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
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        tally = format_tally(game, guild)
                        await game.game_channel.send(
                            f"⏰ **Hammer Update**\n\n"
                            f"Time remaining: **{format_time_remaining(remaining)}**\n\n"
                            f"{tally}"
                        )

async def setup(bot):
    await bot.add_cog(GameplayCog(bot))
