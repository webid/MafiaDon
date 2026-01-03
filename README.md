# MafiaDon - Discord Mafia Game Manager

A Discord bot for managing Mafia game voting and tracking. Automatically detects players based on a role (default: "i play mafia").

## Features

- **Automatic Player Detection**: Players are identified by a Discord role (default: "i play mafia")
- **Category Restriction**: Bot can be limited to a specific category on your server
- **Vote Tracking**: Players use `/vote` with a dropdown menu to select targets
- **Unvote**: Players can remove their vote with `/unvote`
- **Auto-Hammer**: When a majority vote is reached, a 24-hour countdown begins automatically
- **Manual Hammer**: Moderators can trigger the countdown with `/hammer`
- **Tally Updates**: During the hammer countdown, updates are posted every 4 hours
- **Elimination Tracking**: Track eliminated players across the game

## Setup

### 1. Create a Discord Bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" and give it a name
3. Go to the "Bot" section and click "Add Bot"
4. Under the bot's username, click "Reset Token" and copy the token
5. **Important Bot Settings:**
   - Enable "SERVER MEMBERS INTENT" under Privileged Gateway Intents
   - Enable "MESSAGE CONTENT INTENT" under Privileged Gateway Intents

### 2. Invite the Bot to Your Server

1. In the Developer Portal, go to "OAuth2" → "URL Generator"
2. Select scopes: `bot`, `applications.commands`
3. Select bot permissions:
   - Send Messages
   - Embed Links
   - Read Message History
   - Use Slash Commands
4. Copy the generated URL and open it in your browser to invite the bot

### 3. Create the Player Role

1. In your Discord server, create a role called `i play mafia` (or your custom name)
2. Assign this role to all players participating in the mafia game

### 4. Get Your IDs

**Guild (Server) ID:**
1. In Discord, go to User Settings → Advanced → Enable "Developer Mode"
2. Right-click your server name and click "Copy Server ID"

**Category ID (optional):**
1. Right-click the category you want to restrict the bot to
2. Click "Copy Channel ID"

### 5. Configure Environment

Create a `.env` file in the project directory:

```
DISCORD_TOKEN=your_bot_token_here
GUILD_ID=your_guild_id_here
PLAYER_ROLE_NAME=i play mafia
ALLOWED_CATEGORY_ID=123456789012345678
```

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | ✅ | Your bot token from Discord Developer Portal |
| `GUILD_ID` | ✅ | Your server ID (for faster command sync) |
| `PLAYER_ROLE_NAME` | ❌ | Name of the player role (default: "i play mafia") |
| `ALLOWED_CATEGORY_ID` | ❌ | Category ID to restrict bot to (leave empty for all channels) |

### 6. Install Dependencies

```bash
pip install -r requirements.txt
```

### 7. Run the Bot

```bash
python bot.py
```

## Commands

### Game Setup
| Command | Description |
|---------|-------------|
| `/startgame` | Start a new game (auto-detects players with the role) |
| `/players` | Show all players (active and eliminated) |
| `/eliminate @user` | Mark a player as eliminated |
| `/resetvotes` | Clear all votes but keep eliminations |
| `/resetgame` | Reset everything for a new game |

### Voting
| Command | Description |
|---------|-------------|
| `/vote` | Open dropdown to vote for a player |
| `/unvote` | Remove your current vote |
| `/tally` | Show the current vote tally |
| `/hammer` | Manually start the 24-hour countdown |

### Configuration
| Command | Description |
|---------|-------------|
| `/setrole <name>` | Change the player role name |
| `/status` | Show bot configuration and game status |

## How It Works

### Player Detection
- Players are automatically detected based on who has the configured role
- No need to manually add players - just assign the role!
- When the game starts, all members with the role become players

### Voting
- Only players with the role can vote
- Each player can only have one active vote at a time
- Voting again automatically changes your vote
- You cannot vote for yourself
- Eliminated players cannot vote

### Hammer (Elimination)
- **Auto-trigger**: When more than half the active players vote for one person
  - Example: With 9 players, 5 votes = majority → hammer triggered
- **Manual trigger**: Use `/hammer` to force start the countdown
- Once triggered:
  - 24-hour countdown begins
  - Updates posted every 4 hours
  - Votes can still change during countdown
  - When time expires, the player with the most votes is eliminated

### Category Restriction
- Set `ALLOWED_CATEGORY_ID` in your `.env` to restrict the bot
- The bot will only respond to commands in channels within that category
- Leave empty to allow the bot in all channels

## Example Game Flow

1. **Setup**: Create role "i play mafia" and assign to all players
2. **Configure**: Set up `.env` with your category ID if desired
3. **Start**: Use `/startgame` - bot auto-detects all players with the role
4. **Day Phase**: Players discuss and use `/vote` to vote
5. **Hammer**: Majority reached OR `/hammer` used manually
6. **Countdown**: 24 hours with 4-hour tally updates
7. **Elimination**: Time expires, player with most votes is eliminated
8. **Next Day**: Use `/resetvotes` to start new voting round

## Future Features (Coming Soon)

- Night phase management
- Role assignment and secret role messaging
- Game history and statistics
- Multiple concurrent games per server
