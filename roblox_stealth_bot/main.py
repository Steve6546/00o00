import asyncio
import click
import logging
from core.session_manager import SessionManager
from data.database import DatabaseManager
from modules.account_creator import AccountCreator

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

@click.group()
def cli():
    """Stealth Roblox Bot CLI"""
    pass

@cli.command()
@click.option('--count', default=1, help='Number of accounts to create.')
@click.option('--headless/--no-headless', default=True, help='Run in headless mode.')
def gen_accounts(count, headless):
    """Generates new Roblox accounts."""
    async def run():
        db = DatabaseManager()
        session = SessionManager(headless=headless)
        await session.start()
        
        creator = AccountCreator(session, db)
        
        for i in range(count):
            click.echo(f"Creating account {i+1}/{count}...")
            success = await creator.create_account()
            if success:
                click.echo(click.style("Success!", fg='green'))
            else:
                click.echo(click.style("Failed or CAPTCHA encountered.", fg='red'))
        
        await session.stop()

    asyncio.run(run())

@cli.command()
@click.option('--target-id', required=True, help='ID of the Roblox user to follow.')
@click.option('--headless/--no-headless', default=True, help='Run in headless mode.')
def follow_user(target_id, headless):
    """Logs in and follows a target Roblox user."""
    async def run():
        db = DatabaseManager()
        session = SessionManager(headless=headless)
        await session.start()
        
        from modules.follow_bot import FollowBot
        bot = FollowBot(session, db)
        
        click.echo(f"Starting follow task for target: {target_id}...")
        success = await bot.follow_user(target_id)
        
        if success:
            click.echo(click.style("User followed successfully!", fg='green'))
        else:
            click.echo(click.style("Failed to follow user.", fg='red'))
            
        await session.stop()

    asyncio.run(run())

@cli.command()
def init_db():
    """Initializes the database."""
    db = DatabaseManager()
    click.echo("Database initialized.")

if __name__ == '__main__':
    cli()
