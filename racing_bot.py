import discord
from discord.ext import commands, tasks
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from datetime import datetime, timezone
import json
import re
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = 'MTM5NTkxNDE1NTA5NzE5ODY3Mw.GgNN-I.apsbhLK0Wy5Hw9LyvqWpp68bWgsi7Gl8pGHB1U'  # Replace with your bot token
CHANNEL_ID = 1395915660458201148  

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

class RacingScraper:
    def __init__(self):
        self.session = None
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self.headers)
        return self.session
    
    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def scrape_racing_post_today(self):
        """Scrape today's UK horse racing from Racing Post"""
        try:
            session = await self.get_session()
            url = "https://www.racingpost.com/racecards/"
            
            async with session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    return self.parse_racing_post_html(html)
                else:
                    logger.error(f"Failed to fetch Racing Post data: {response.status}")
                    return []
        except Exception as e:
            logger.error(f"Error scraping Racing Post: {e}")
            return []
    
    def parse_racing_post_html(self, html):
        """Parse Racing Post HTML to extract race information"""
        soup = BeautifulSoup(html, 'html.parser')
        races = []
        
        try:
            # Look for race cards - Racing Post structure may vary
            race_cards = soup.find_all('div', class_=re.compile(r'racecard|race-card'))
            
            if not race_cards:
                # Alternative selectors for Racing Post
                race_cards = soup.find_all('div', {'data-testid': re.compile(r'race')})
            
            if not race_cards:
                # Look for any div containing race information
                race_cards = soup.find_all('div', string=re.compile(r'\d{2}:\d{2}'))
            
            for card in race_cards[:20]:  # Limit to 20 races
                race_info = self.extract_race_info(card)
                if race_info:
                    races.append(race_info)
            
            # If no races found with the above method, try a different approach
            if not races:
                races = self.fallback_parse_method(soup)
                
        except Exception as e:
            logger.error(f"Error parsing Racing Post HTML: {e}")
        
        return races
    
    def extract_race_info(self, card_element):
        """Extract race information from a card element"""
        try:
            # Try to find time
            time_elem = card_element.find(string=re.compile(r'\d{2}:\d{2}'))
            if not time_elem:
                time_pattern = re.search(r'(\d{1,2}:\d{2})', card_element.get_text())
                race_time = time_pattern.group(1) if time_pattern else "Unknown"
            else:
                time_match = re.search(r'(\d{1,2}:\d{2})', time_elem)
                race_time = time_match.group(1) if time_match else "Unknown"
            
            # Try to find course/venue
            text = card_element.get_text()
            
            # Common UK racecourses
            uk_courses = [
                'Ascot', 'Aintree', 'Cheltenham', 'Epsom', 'Goodwood', 'Newmarket',
                'York', 'Doncaster', 'Chester', 'Bath', 'Brighton', 'Catterick',
                'Chepstow', 'Exeter', 'Fakenham', 'Ffos Las', 'Fontwell',
                'Haydock', 'Hereford', 'Hexham', 'Huntingdon', 'Kempton',
                'Leicester', 'Lingfield', 'Ludlow', 'Market Rasen', 'Musselburgh',
                'Newcastle', 'Newton Abbot', 'Nottingham', 'Perth', 'Plumpton',
                'Pontefract', 'Redcar', 'Ripon', 'Salisbury', 'Sandown',
                'Sedgefield', 'Southwell', 'Stratford', 'Taunton', 'Thirsk',
                'Uttoxeter', 'Warwick', 'Wetherby', 'Wincanton', 'Windsor',
                'Wolverhampton', 'Worcester'
            ]
            
            course = "Unknown Course"
            for uc in uk_courses:
                if uc.lower() in text.lower():
                    course = uc
                    break
            
            # Try to extract race name/type
            race_name = "Horse Race"
            if "handicap" in text.lower():
                race_name = "Handicap"
            elif "stakes" in text.lower():
                race_name = "Stakes Race"
            elif "maiden" in text.lower():
                race_name = "Maiden"
            elif "novice" in text.lower():
                race_name = "Novice"
            
            return {
                'time': race_time,
                'course': course,
                'name': race_name,
                'full_text': text.strip()[:100]  # Keep some context
            }
            
        except Exception as e:
            logger.error(f"Error extracting race info: {e}")
            return None
    
    def fallback_parse_method(self, soup):
        """Fallback method to parse racing data"""
        races = []
        try:
            # Look for any element containing time patterns and course names
            all_text = soup.get_text()
            lines = all_text.split('\n')
            
            for line in lines:
                if re.search(r'\d{1,2}:\d{2}', line) and len(line) < 200:
                    time_match = re.search(r'(\d{1,2}:\d{2})', line)
                    if time_match:
                        races.append({
                            'time': time_match.group(1),
                            'course': 'Various UK Courses',
                            'name': 'Horse Race',
                            'full_text': line.strip()
                        })
                        
                        if len(races) >= 10:  # Limit results
                            break
                            
        except Exception as e:
            logger.error(f"Error in fallback parse: {e}")
        
        return races

# Initialize scraper
scraper = RacingScraper()

@bot.event
async def on_ready():
    print(f'{bot.user} has logged in to Discord!')
    print(f'Bot is in {len(bot.guilds)} guilds')
    daily_racing_update.start()  # Start the daily update task

@bot.command(name='races')
async def get_races(ctx):
    """Manual command to get today's races"""
    await ctx.send("🏇 Fetching today's UK horse racing schedule...")
    
    races = await scraper.scrape_racing_post_today()
    
    if not races:
        await ctx.send("❌ Sorry, couldn't fetch racing data at the moment. Please try again later.")
        return
    
    # Format the races into a nice embed
    embed = discord.Embed(
        title="🏇 Today's UK Horse Racing",
        description=f"Found {len(races)} races scheduled for today",
        color=0x00ff00,
        timestamp=datetime.now(timezone.utc)
    )
    
    # Group races by time for better display
    race_text = ""
    for race in races[:15]:  # Limit to 15 races to avoid message limit
        race_text += f"**{race['time']}** - {race['course']} ({race['name']})\n"
    
    if race_text:
        embed.add_field(name="Race Schedule", value=race_text, inline=False)
    else:
        embed.add_field(name="No Races", value="No races found for today", inline=False)
    
    embed.set_footer(text="Data scraped from Racing Post")
    
    try:
        await ctx.send(embed=embed)
    except discord.HTTPException:
        # If embed is too long, send as plain text
        message = f"🏇 **Today's UK Horse Racing:**\n\n{race_text}"
        await ctx.send(message[:2000])  # Discord message limit

@tasks.loop(hours=24)
async def daily_racing_update():
    """Send daily racing update at 8 AM"""
    now = datetime.now()
    if now.hour == 8:  # 8 AM
        channel = bot.get_channel(CHANNEL_ID)
        if channel:
            races = await scraper.scrape_racing_post_today()
            
            if races:
                embed = discord.Embed(
                    title="🏇 Good Morning! Today's UK Horse Racing",
                    description=f"Here are today's {len(races)} scheduled races:",
                    color=0x00ff00,
                    timestamp=datetime.now(timezone.utc)
                )
                
                race_text = ""
                for race in races[:15]:
                    race_text += f"**{race['time']}** - {race['course']} ({race['name']})\n"
                
                if race_text:
                    embed.add_field(name="Race Schedule", value=race_text, inline=False)
                
                embed.set_footer(text="Daily update from Racing Post")
                
                try:
                    await channel.send(embed=embed)
                except Exception as e:
                    logger.error(f"Error sending daily update: {e}")

@bot.command(name='help_racing')
async def help_racing(ctx):
    """Show available racing commands"""
    help_embed = discord.Embed(
        title="🏇 Horse Racing Bot Commands",
        color=0x0099ff
    )
    
    help_embed.add_field(
        name="!races", 
        value="Get today's UK horse racing schedule", 
        inline=False
    )
    
    help_embed.add_field(
        name="Daily Updates", 
        value="The bot automatically posts daily racing schedules at 8 AM", 
        inline=False
    )
    
    help_embed.add_field(
        name="Data Source", 
        value="Racing data is scraped from Racing Post (racingpost.com)", 
        inline=False
    )
    
    await ctx.send(embed=help_embed)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return  # Ignore command not found errors
    
    logger.error(f"Command error: {error}")
    await ctx.send("An error occurred while processing the command.")

# Cleanup function
@bot.event
async def on_disconnect():
    await scraper.close_session()

# Run the bot
if __name__ == "__main__":
    try:
        bot.run(BOT_TOKEN)
    except KeyboardInterrupt:
        print("Bot shutting down...")
        asyncio.run(scraper.close_session())