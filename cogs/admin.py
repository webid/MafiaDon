import discord
from discord import app_commands
from discord.ext import commands
from utils import (
    get_game, is_manager_or_mod, is_in_allowed_category, has_player_role,
    get_players_with_role, GameState, games, PLAYER_ROLE_NAME
)

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, interaction: discord.Interaction) -> bool:
        """Global check for all commands in this Cog."""
        # 1. Check category
        if not is_in_allowed_category(interaction.channel):
            await interaction.response.send_message(
                "❌ This command can only be used in the Mafia game channels!",
                ephemeral=True
            )
            return False

        # 2. Check permissions (Manager/Mod)
        if not is_manager_or_mod(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission to use this command! (Managers/Mods only)",
                ephemeral=True
            )
            return False
        
        return True

    @app_commands.command(name="startgame", description="Start a new Mafia game with players who have the player role")
    async def startgame(self, interaction: discord.Interaction):
        """Start a new game, automatically detecting players with the mafia role."""
        # Note: checks are handled by cog_check (mostly), but app_commands don''t use cog_check automatically
        # in the same way as prefix commands. 
        # However, for hybrid/slash commands, we often need explicit checks or a global error handler.
        # But wait, app_commands.checks... 
        #
        # Actually, let's keep the explicit check inside the command for now if cog_check behaves differently 
        # for tree commands without binding. But idiomatic way is often decorators.
        # 
        # Let's trust the user request to "optimize". Optimizing "check permissions code" 
        # usually implies using a decorator check.
        
        # Let's apply the checks explicitly at the top of logic OR use the decorator.
        # Since I put logic in cog_check, it only works for `commands.command`.
        # For `app_commands`, we need `app_commands.check`.
        # But `app_commands.check` doesn't support custom error messages easily without an error handler.
        # 
        # To satisfy "optimize" and "always the same", let's use a private helper method or just call the utility.
        # BUT, the user specifically showed the if block.
        # So I will use the `is_manager_or_mod` utility I already have, but wrapped in a common check function
        # inside the class or just re-use the utility function.
        #
        # Re-reading the request: "the check permissions code is always the same, can we optimize ?"
        # 
        # I will use a custom check decorator pattern for app commands.

        pass # This is just a comment block in my thought process. 
             # I will write the actual code below.

    # Redefining checks to be app_command friendly
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
         # This is called for app commands in this cog!
        if not is_in_allowed_category(interaction.channel):
            await interaction.response.send_message(
                "❌ This command can only be used in the Mafia game channels!",
                ephemeral=True
            )
            return False

        if not is_manager_or_mod(interaction):
            await interaction.response.send_message(
                "❌ You do not have permission to use this command! (Managers/Mods only)",
                ephemeral=True
            )
            return False
        return True

    @app_commands.command(name="eliminate", description="Mark a player as eliminated (moderator only)")
    @app_commands.describe(player="The player to eliminate")
    async def eliminate(self, interaction: discord.Interaction, player: discord.Member):
        """Mark a player as eliminated from the game."""
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

    @app_commands.command(name="resetgame", description="Reset the current game (clears all votes and eliminations)")
    async def resetgame(self, interaction: discord.Interaction):
        """Reset the current game."""
        games[interaction.guild.id] = GameState()
        
        await interaction.response.send_message(
            "🔄 Game has been reset! All votes and eliminations cleared.\n"
            "Use `/startgame` to begin a new game."
        )

    @app_commands.command(name="resetvotes", description="Reset all votes but keep game state")
    async def resetvotes(self, interaction: discord.Interaction):
        """Reset votes but keep eliminations."""
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

    @app_commands.command(name="setrole", description="Set the player role name (default: 'i play mafia')")
    @app_commands.describe(role_name="The name of the role that identifies mafia players")
    async def setrole(self, interaction: discord.Interaction, role_name: str):
        """Change the player role name."""
        global PLAYER_ROLE_NAME
        # Note: Modifying global config in utils might be tricky if not careful, 
        # but for this simple bot it works if we import it right or modify the module variable.
        # Better to update `utils.PLAYER_ROLE_NAME` directly.
        import utils
        
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
            utils.PLAYER_ROLE_NAME = role_name
            players = get_players_with_role(interaction.guild)
            await interaction.response.send_message(
                f"✅ Player role set to **{role_name}**!\n"
                f"Found {len(players)} players with this role."
            )

    @app_commands.command(name="startgame", description="Start a new Mafia game with players who have the player role")
    async def startgame(self, interaction: discord.Interaction):
        """Start a new game, automatically detecting players with the mafia role."""
        game = get_game(interaction.guild.id)
        
        # Check for player role
        role = None
        # We need to get role helper from utils again since I didn't import the function to store it, just used it.
        from utils import get_player_role
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

async def setup(bot):
    await bot.add_cog(AdminCog(bot))
