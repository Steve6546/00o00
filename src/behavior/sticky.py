import asyncio
import random
import logging
from src.behavior.interaction import Interaction

logger = logging.getLogger(__name__)

async def simulate_sticky_activity(page, interaction: Interaction):
    """
    Simulates random 'human' activity after creation or login to look less like a bot.
    """
    logger.info("Performing sticky activity to simulate real usage...")
    
    actions = [
        "https://www.roblox.com/catalog",
        "https://www.roblox.com/discover",
        "https://www.roblox.com/create"
    ]
    
    # Visit 1-2 random pages
    for _ in range(random.randint(1, 2)):
        target = random.choice(actions)
        try:
            logger.info(f"Visiting {target}...")
            await page.goto(target)
            await interaction.random_pause(2, 5)
            await interaction.human_input.natural_scroll()
            
            # Randomly click a discovery item (game) but don't play
            if "discover" in target:
                 games = await page.query_selector_all(".game-card-link")
                 if games:
                     selected_game = random.choice(games[:10])
                     await selected_game.scroll_into_view_if_needed()
                     await interaction.random_pause(1, 2)
                     # Hover for a bit
                     box = await selected_game.bounding_box()
                     if box:
                         await interaction.human_input.move_mouse(box['x'] + box['width']/2, box['y'] + box['height']/2)
        except Exception as e:
            logger.warning(f"Sticky activity step failed: {e}")
            
    logger.info("Sticky activity completed.")

