"""
Roblox Bot CLI - Unified command-line interface.

Usage:
    python cli.py create --count 5
    python cli.py follow --target 123456 --count 10
    python cli.py status
    python cli.py accounts
"""

import asyncio
import click
import logging
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# Setup
console = Console()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%H:%M:%S'
)


@click.group()
@click.option('--config', '-c', default='config/config.yaml', help='Config file path')
@click.option('--headless/--no-headless', default=False, help='Run browser headless')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.pass_context
def cli(ctx, config, headless, verbose):
    """🤖 Roblox Automation System - Intelligent Bot Control"""
    ctx.ensure_object(dict)
    ctx.obj['config'] = config
    ctx.obj['headless'] = headless
    ctx.obj['verbose'] = verbose
    
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)


@cli.command()
@click.option('--count', '-n', default=1, help='Number of accounts to create')
@click.option('--proxy/--no-proxy', default=False, help='Use proxy')
@click.pass_context
def create(ctx, count, proxy):
    """📝 Create new Roblox accounts"""
    
    console.print(Panel.fit(
        f"[bold blue]Creating {count} Account(s)[/bold blue]\n"
        f"Proxy: {'✅ Enabled' if proxy else '❌ Disabled'}",
        title="🤖 Account Creation"
    ))
    
    asyncio.run(_create_accounts(count, proxy, ctx.obj))


async def _create_accounts(count: int, use_proxy: bool, options: dict):
    """Execute account creation."""
    from src.control.commander import Commander
    
    commander = Commander(options['config'], headless=options.get('headless'))
    
    try:
        await commander.initialize()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task(f"Creating accounts...", total=count)
            
            result = await commander.create_accounts(count, use_proxy)
            
            progress.update(task, completed=count)
        
        if result:
            # Show results
            table = Table(title="Results")
            table.add_column("Account", style="cyan")
            table.add_column("Status", style="green")
            
            for r in result.results:
                if r.get('success'):
                    table.add_row(r.get('username', 'N/A'), "✅ Created")
                else:
                    table.add_row("Failed", f"❌ {r.get('error', 'Unknown')}")
            
            console.print(table)
            console.print(f"\n[bold green]✅ Created: {result.completed}[/bold green] | "
                         f"[bold red]❌ Failed: {result.failed}[/bold red]")
    
    finally:
        await commander.shutdown()


@cli.command()
@click.argument('target')
@click.option('--count', '-n', default=1, help='Number of accounts to use')
@click.option('--is-id', is_flag=True, help='Target is a UserID (not username)')
@click.pass_context
def follow(ctx, target, count, is_id):
    """👥 Follow a user with multiple accounts"""
    
    # Auto-detect: if target is all digits, treat as ID
    if target.isdigit():
        is_id = True
        console.print(f"[dim]Auto-detected target as User ID[/dim]")
    
    console.print(Panel.fit(
        f"[bold blue]Following: {target}[/bold blue]\n"
        f"Accounts: {count}\n"
        f"Target Type: {'UserID' if is_id else 'Username'}",
        title="👥 Follow User"
    ))
    
    asyncio.run(_follow_user(target, count, is_id, ctx.obj))


async def _follow_user(target: str, count: int, is_id: bool, options: dict):
    """Execute follow operation."""
    from src.control.commander import Commander
    
    commander = Commander(options['config'], headless=options.get('headless'))
    
    try:
        await commander.initialize()
        
        result = await commander.follow_user(target, count, is_id)
        
        if result:
            table = Table(title="Follow Results")
            table.add_column("Account", style="cyan")
            table.add_column("Status")
            
            for r in result.results:
                status = "✅ Followed" if r['success'] else (
                    "⏭️ Already Following" if r.get('already_following') else f"❌ {r.get('error', 'Failed')}"
                )
                table.add_row(r.get('account', 'N/A'), status)
            
            console.print(table)
    
    finally:
        await commander.shutdown()


@cli.command()
@click.pass_context
def status(ctx):
    """📊 Show system status"""
    
    asyncio.run(_show_status(ctx.obj))


async def _show_status(options: dict):
    """Show system status."""
    from src.control.commander import Commander
    from data.database import DatabaseManager, Account
    
    db = DatabaseManager()
    
    # Account stats
    total_accounts = Account.select().count()
    active_accounts = Account.select().where(Account.status == 'active').count()
    
    # Create status panel
    status_text = f"""
[bold]System Status[/bold]
  Config: {options['config']}
  
[bold]Accounts[/bold]
  Total: {total_accounts}
  Active: {active_accounts}
"""
    
    console.print(Panel(status_text, title="📊 Bot Status"))
    
    # Recent accounts
    accounts = list(Account.select().order_by(Account.created_at.desc()).limit(5))
    
    if accounts:
        table = Table(title="Recent Accounts")
        table.add_column("Username", style="cyan")
        table.add_column("Status")
        table.add_column("Follows")
        table.add_column("Created")
        
        for a in accounts:
            table.add_row(
                a.username,
                a.status,
                str(a.follow_count),
                str(a.created_at.strftime("%Y-%m-%d %H:%M"))
            )
        
        console.print(table)
    
    db.close()


@cli.command()
@click.option('--limit', '-l', default=20, help='Number of accounts to show')
@click.pass_context
def accounts(ctx, limit):
    """👤 List all accounts"""
    
    from data.database import DatabaseManager, Account
    
    db = DatabaseManager()
    accounts_list = list(Account.select().order_by(Account.created_at.desc()).limit(limit))
    
    if not accounts_list:
        console.print("[yellow]No accounts found. Create some with 'create' command.[/yellow]")
        return
    
    table = Table(title=f"Accounts (showing {len(accounts_list)})")
    table.add_column("ID", style="dim")
    table.add_column("Username", style="cyan")
    table.add_column("Status")
    table.add_column("Follows", justify="right")
    table.add_column("Created")
    
    for a in accounts_list:
        status_style = "green" if a.status == "active" else "yellow"
        table.add_row(
            str(a.id),
            a.username,
            f"[{status_style}]{a.status}[/{status_style}]",
            str(a.follow_count),
            a.created_at.strftime("%Y-%m-%d %H:%M")
        )
    
    console.print(table)
    db.close()


@cli.command()
@click.pass_context
def init(ctx):
    """🔧 Initialize database and system"""
    
    from data.database import DatabaseManager
    
    console.print("[bold]Initializing system...[/bold]")
    
    db = DatabaseManager()
    console.print("  ✅ Database initialized")
    
    # Check config
    import os
    if os.path.exists(ctx.obj['config']):
        console.print(f"  ✅ Config found: {ctx.obj['config']}")
    else:
        console.print(f"  ⚠️  Config not found: {ctx.obj['config']}")
    
    console.print("\n[bold green]System ready![/bold green]")
    db.close()


@cli.command()
@click.argument('target')
@click.option('--accounts', '-a', default=5, help='Accounts to create')
@click.option('--follows', '-f', default=1, help='Follows per account')
@click.pass_context
def auto(ctx, target, accounts, follows):
    """🚀 Auto mode: Create accounts and follow target"""
    
    console.print(Panel.fit(
        f"[bold blue]Auto Mode[/bold blue]\n"
        f"Target: {target}\n"
        f"Accounts to create: {accounts}\n"
        f"Follows per account: {follows}",
        title="🚀 Auto Mode"
    ))
    
    asyncio.run(_auto_mode(target, accounts, follows, ctx.obj))


async def _auto_mode(target: str, account_count: int, follows_per: int, options: dict):
    """Execute auto mode."""
    from src.control.commander import Commander
    
    commander = Commander(options['config'], headless=options.get('headless'))
    
    try:
        await commander.initialize()
        
        # Step 1: Create accounts
        console.print("\n[bold]Step 1: Creating accounts...[/bold]")
        create_result = await commander.create_accounts(account_count)
        console.print(f"  Created: {create_result.completed}, Failed: {create_result.failed}")
        
        # Step 2: Follow with each account
        console.print(f"\n[bold]Step 2: Following {target}...[/bold]")
        follow_result = await commander.follow_user(target, follows_per)
        console.print(f"  Followed: {follow_result.completed}, Failed: {follow_result.failed}")
        
        console.print("\n[bold green]✅ Auto mode complete![/bold green]")
    
    finally:
        await commander.shutdown()


# =============================================================================
# ACCOUNTS COMMAND GROUP  
# =============================================================================

@cli.group()
def accounts():
    """📊 Account Management - View and manage created accounts"""
    pass


@accounts.command(name='list')
def accounts_list():
    """List all accounts with status and follow counts"""
    from src.services.health_checker import get_account_summary
    
    summary = get_account_summary(None)
    
    console.print(Panel.fit(
        f"[bold]Total: {summary['total']}[/bold] | "
        f"[green]Active: {summary['active']}[/green] | "
        f"[red]Banned: {summary['banned']}[/red] | "
        f"[blue]♂ Male: {summary['male']}[/blue] | "
        f"[magenta]♀ Female: {summary['female']}[/magenta]",
        title="📊 Accounts Summary"
    ))
    
    table = Table(title="All Accounts")
    table.add_column("Username", style="cyan")
    table.add_column("Gender")
    table.add_column("Status")
    table.add_column("Follows", justify="center")
    table.add_column("Created", style="dim")
    
    for acc in summary['accounts']:
        status_style = "red" if acc['is_banned'] else "green"
        gender_icon = "♂" if acc['gender'] == 'male' else ("♀" if acc['gender'] == 'female' else "?")
        table.add_row(
            acc['username'],
            f"{gender_icon} {acc['gender']}",
            f"[{status_style}]{acc['status']}[/{status_style}]",
            str(acc['follow_count']),
            acc['created_at'] or "N/A"
        )
    
    console.print(table)


@accounts.command(name='info')
@click.argument('username')
def accounts_info(username):
    """Show detailed info for a specific account"""
    from src.services.health_checker import get_account_details
    
    details = get_account_details(username)
    if not details:
        console.print(f"[red]Account '{username}' not found[/red]")
        return
    
    gender_icon = "♂" if details['gender'] == 'male' else ("♀" if details['gender'] == 'female' else "?")
    console.print(Panel(
        f"[bold cyan]{details['username']}[/bold cyan]\n\n"
        f"Status: {details['status']}\n"
        f"Gender: {gender_icon} {details['gender']}\n"
        f"[bold]Following: {details['follow_count']} accounts[/bold]",
        title="📋 Account Details"
    ))
    
    if details['follows']:
        table = Table(title=f"Follows ({len(details['follows'])})")
        table.add_column("Target ID")
        table.add_column("Username")
        table.add_column("Verified")
        for f in details['follows']:
            table.add_row(f['target_id'], f['target_username'] or "N/A", "✅" if f['verified'] else "❓")
        console.print(table)


@accounts.command(name='health-check')
def accounts_health_check():
    """Check health status of all accounts"""
    from data.database import Account
    import datetime
    
    console.print("[bold]🔍 Running health check...[/bold]\n")
    for account in Account.select():
        icon = "✅" if not account.is_banned else "❌"
        console.print(f"  {icon} {account.username}: {account.status}")
        account.last_health_check = datetime.datetime.now()
        account.save()
    console.print("\n[dim]Health check complete[/dim]")


if __name__ == '__main__':
    cli(obj={})
