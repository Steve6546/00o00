"""
Inspector Module - نظام التفتيش الشامل
======================================

Provides comprehensive inspection and health checking for:
- Accounts (individual and bulk)
- Proxies
- System status
- Task history

Usage:
    from src.control.inspector import Inspector
    inspector = Inspector()
    inspector.inspect_account("username")
"""

import sys
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from rich.console import Console
from rich.table import Table
from rich.panel import Panel


@dataclass
class AccountHealth:
    """Account health assessment result."""
    status: str
    icon: str
    score: int  # 0-100
    issues: List[str]
    recommendations: List[str]


@dataclass
class InspectionReport:
    """Generic inspection report."""
    success: bool
    timestamp: datetime
    data: Dict[str, Any]
    warnings: List[str]
    errors: List[str]


class Inspector:
    """
    Comprehensive system inspection and health checking.
    
    Features:
    - Account inspection with detailed reports
    - Proxy pool analysis
    - System health monitoring
    - Performance metrics
    """
    
    def __init__(self, console: Console = None):
        self.console = console or Console()
        self._init_database()
    
    def _init_database(self):
        """Initialize database connection."""
        try:
            from data.database import (
                DatabaseManager, Account, Proxy, TaskLog, FollowRecord
            )
            self.db = DatabaseManager()
            self.Account = Account
            self.Proxy = Proxy
            self.TaskLog = TaskLog
            self.FollowRecord = FollowRecord
            self.db_connected = True
        except Exception as e:
            self.console.print(f"[yellow]⚠️ Database not available: {e}[/yellow]")
            self.db = None
            self.db_connected = False
    
    # =========================================================================
    # ACCOUNT INSPECTION
    # =========================================================================
    
    def inspect_account(self, username: str, verbose: bool = True) -> Optional[InspectionReport]:
        """
        Detailed inspection of a single account.
        
        Args:
            username: Account username to inspect
            verbose: Whether to print results to console
            
        Returns:
            InspectionReport with account data
        """
        if not self.db_connected:
            self.console.print("[red]❌ Database not connected[/red]")
            return None
        
        try:
            account = self.Account.get_or_none(self.Account.username == username)
            if not account:
                self.console.print(f"[red]❌ Account '{username}' not found[/red]")
                self._suggest_similar_accounts(username)
                return None
            
            # Get follow records
            follows = list(self.FollowRecord.select().where(
                self.FollowRecord.account == account
            ).order_by(self.FollowRecord.followed_at.desc()))
            
            # Assess health
            health = self._assess_account_health(account)
            
            # Build report data
            report_data = {
                'username': account.username,
                'status': account.status,
                'gender': account.gender,
                'is_banned': account.is_banned,
                'created_at': account.created_at,
                'last_used': account.last_used,
                'follow_count': account.follow_count,
                'follows': [
                    {
                        'target_id': f.target_id,
                        'target_username': f.target_username,
                        'followed_at': f.followed_at,
                        'verified': f.verified
                    }
                    for f in follows
                ],
                'health': health,
                'proxy_used': account.proxy_used,
                'cooldown_until': account.cooldown_until,
            }
            
            if verbose:
                self._print_account_report(account, follows, health)
            
            return InspectionReport(
                success=True,
                timestamp=datetime.now(),
                data=report_data,
                warnings=health.issues,
                errors=[]
            )
            
        except Exception as e:
            self.console.print(f"[red]Error inspecting account: {e}[/red]")
            return None
    
    def _print_account_report(self, account, follows: List, health: AccountHealth):
        """Print formatted account report."""
        status_icon = "✅" if account.status == "active" else ("❌" if account.is_banned else "⚠️")
        gender_icon = "♂" if account.gender == 'male' else ("♀" if account.gender == 'female' else "❓")
        
        # Calculate age
        age = datetime.now() - account.created_at
        age_str = f"{age.days}d {age.seconds // 3600}h"
        
        # Last used
        if account.last_used:
            last_delta = datetime.now() - account.last_used
            last_str = f"{last_delta.days}d ago" if last_delta.days > 0 else f"{last_delta.seconds // 3600}h ago"
        else:
            last_str = "Never"
        
        info_text = f"""[bold cyan]{account.username}[/bold cyan]

[bold]📋 Basic Info:[/bold]
  Status: {status_icon} {account.status}
  Gender: {gender_icon} {account.gender or 'Unknown'}
  Created: {account.created_at.strftime('%Y-%m-%d %H:%M')}
  Age: {age_str}
  Last Used: {last_str}

[bold]📊 Statistics:[/bold]
  Follows: [bold]{account.follow_count}[/bold] accounts followed
  Health: {health.icon} {health.status} ({health.score}/100)
  
[bold]🔒 Security:[/bold]
  Banned: {'❌ Yes' if account.is_banned else '✅ No'}
  Cooldown: {account.cooldown_until.strftime('%H:%M') if account.cooldown_until and account.cooldown_until > datetime.now() else '✅ None'}
  
[bold]🌐 Technical:[/bold]
  Proxy: {account.proxy_used or 'None'}
"""
        
        self.console.print(Panel(info_text, title=f"🔍 Account Inspection: {account.username}", border_style="cyan"))
        
        # Show issues and recommendations
        if health.issues:
            issues_text = "\n".join(f"  ⚠️ {issue}" for issue in health.issues)
            self.console.print(Panel(issues_text, title="⚠️ Issues", border_style="yellow"))
        
        if health.recommendations:
            rec_text = "\n".join(f"  💡 {rec}" for rec in health.recommendations)
            self.console.print(Panel(rec_text, title="💡 Recommendations", border_style="blue"))
        
        # Follow history
        if follows:
            table = Table(title=f"📋 Follow History ({len(follows)} total)", box=None)
            table.add_column("Target", style="cyan")
            table.add_column("Date", style="dim")
            table.add_column("Verified", justify="center")
            
            for f in follows[:10]:
                table.add_row(
                    f.target_username or f.target_id,
                    f.followed_at.strftime("%Y-%m-%d %H:%M"),
                    "✅" if f.verified else "❓"
                )
            
            if len(follows) > 10:
                table.add_row("...", f"({len(follows) - 10} more)", "")
            
            self.console.print(table)
    
    def _assess_account_health(self, account) -> AccountHealth:
        """
        Assess account health with detailed scoring.
        
        Returns:
            AccountHealth with status, score, issues, and recommendations
        """
        score = 100
        issues = []
        recommendations = []
        
        # Check banned status
        if account.is_banned:
            return AccountHealth(
                status="Banned",
                icon="🔴",
                score=0,
                issues=["Account has been banned"],
                recommendations=["Create a new account", "Use different proxy for new accounts"]
            )
        
        # Check status
        if account.status != "active":
            score -= 30
            issues.append(f"Account status is '{account.status}'")
        
        # Check cooldown
        if account.cooldown_until and account.cooldown_until > datetime.now():
            score -= 10
            issues.append("Account is on cooldown")
            recommendations.append("Wait for cooldown to expire before using")
        
        # Check usage
        if account.follow_count > 50:
            score -= 20
            issues.append("High follow count may trigger detection")
            recommendations.append("Consider letting this account rest")
        elif account.follow_count > 30:
            score -= 10
            issues.append("Moderate follow count")
        
        # Check last health check
        if account.last_health_check:
            days_since = (datetime.now() - account.last_health_check).days
            if days_since > 7:
                score -= 5
                recommendations.append("Run health check to verify account status")
        
        # Determine status
        if score >= 80:
            status, icon = "Excellent", "🟢"
        elif score >= 60:
            status, icon = "Good", "🟢"
        elif score >= 40:
            status, icon = "Fair", "🟡"
        elif score >= 20:
            status, icon = "Poor", "🟠"
        else:
            status, icon = "Critical", "🔴"
        
        return AccountHealth(
            status=status,
            icon=icon,
            score=max(0, score),
            issues=issues,
            recommendations=recommendations
        )
    
    def _suggest_similar_accounts(self, username: str):
        """Suggest similar account names."""
        try:
            accounts = list(self.Account.select().limit(100))
            similar = [a.username for a in accounts 
                      if username.lower() in a.username.lower() 
                      or a.username.lower().startswith(username[:3].lower())][:5]
            if similar:
                self.console.print(f"\n[dim]Did you mean: {', '.join(similar)}?[/dim]")
        except:
            pass
    
    def inspect_all_accounts(self, limit: int = 100) -> Optional[InspectionReport]:
        """Full inspection of all accounts."""
        if not self.db_connected:
            self.console.print("[red]❌ Database not connected[/red]")
            return None
        
        try:
            accounts = list(self.Account.select()
                          .order_by(self.Account.created_at.desc())
                          .limit(limit))
            
            if not accounts:
                self.console.print("[yellow]No accounts found. Create some first![/yellow]")
                return None
            
            # Aggregate stats
            total = len(accounts)
            active = sum(1 for a in accounts if a.status == 'active')
            banned = sum(1 for a in accounts if a.is_banned)
            male = sum(1 for a in accounts if a.gender == 'male')
            female = sum(1 for a in accounts if a.gender == 'female')
            total_follows = sum(a.follow_count for a in accounts)
            
            # Health distribution
            health_stats = {'Excellent': 0, 'Good': 0, 'Fair': 0, 'Poor': 0, 'Critical': 0, 'Banned': 0}
            for acc in accounts:
                health = self._assess_account_health(acc)
                health_stats[health.status] = health_stats.get(health.status, 0) + 1
            
            # Print summary
            summary = Panel(
                f"[bold]Total:[/bold] {total} | "
                f"[green]Active:[/green] {active} | "
                f"[red]Banned:[/red] {banned} | "
                f"[blue]♂ Male:[/blue] {male} | "
                f"[magenta]♀ Female:[/magenta] {female} | "
                f"[cyan]Total Follows:[/cyan] {total_follows}",
                title="📊 Accounts Summary"
            )
            self.console.print(summary)
            
            # Health distribution
            health_str = " | ".join(f"{k}: {v}" for k, v in health_stats.items() if v > 0)
            self.console.print(f"[dim]Health: {health_str}[/dim]\n")
            
            # Detailed table
            table = Table(title=f"All Accounts ({total})")
            table.add_column("#", style="dim", width=4)
            table.add_column("Username", style="cyan")
            table.add_column("Status", width=10)
            table.add_column("Gender", width=8)
            table.add_column("Follows", justify="right", width=8)
            table.add_column("Health", width=14)
            table.add_column("Created", style="dim", width=12)
            
            for i, acc in enumerate(accounts, 1):
                status_style = "green" if acc.status == "active" else ("red" if acc.is_banned else "yellow")
                gender_icon = "♂" if acc.gender == 'male' else ("♀" if acc.gender == 'female' else "?")
                health = self._assess_account_health(acc)
                
                table.add_row(
                    str(i),
                    acc.username,
                    f"[{status_style}]{acc.status}[/{status_style}]",
                    f"{gender_icon} {acc.gender or '?'}",
                    str(acc.follow_count),
                    f"{health.icon} {health.status}",
                    acc.created_at.strftime("%m/%d %H:%M")
                )
            
            self.console.print(table)
            
            return InspectionReport(
                success=True,
                timestamp=datetime.now(),
                data={
                    'total': total,
                    'active': active,
                    'banned': banned,
                    'male': male,
                    'female': female,
                    'total_follows': total_follows,
                    'health_distribution': health_stats
                },
                warnings=[],
                errors=[]
            )
            
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return None
    
    # =========================================================================
    # PROXY INSPECTION
    # =========================================================================
    
    def inspect_proxies(self) -> Optional[InspectionReport]:
        """Inspect proxy pool."""
        if not self.db_connected:
            self.console.print("[red]❌ Database not connected[/red]")
            return None
        
        try:
            proxies = list(self.Proxy.select().order_by(self.Proxy.latency_ms.asc()))
            
            if not proxies:
                self.console.print("[yellow]No proxies found[/yellow]")
                return None
            
            working = [p for p in proxies if p.is_working]
            failed = [p for p in proxies if not p.is_working]
            
            avg_latency = sum(p.latency_ms or 0 for p in working) / max(len(working), 1)
            total_success = sum(p.success_count for p in proxies)
            total_fails = sum(p.fail_count for p in proxies)
            
            # Summary
            summary = Panel(
                f"[bold]Total:[/bold] {len(proxies)} | "
                f"[green]Working:[/green] {len(working)} | "
                f"[red]Failed:[/red] {len(failed)} | "
                f"[cyan]Avg Latency:[/cyan] {avg_latency:.0f}ms | "
                f"[green]Success:[/green] {total_success} | "
                f"[red]Fails:[/red] {total_fails}",
                title="🌐 Proxy Pool Summary"
            )
            self.console.print(summary)
            
            # Table
            table = Table(title="Proxy List")
            table.add_column("Server", style="cyan", max_width=40)
            table.add_column("Status", width=12)
            table.add_column("Latency", justify="right", width=10)
            table.add_column("Success", justify="right", width=8)
            table.add_column("Fails", justify="right", width=8)
            table.add_column("Rate", justify="right", width=8)
            table.add_column("Source", style="dim", width=10)
            
            for proxy in proxies[:25]:
                status = "[green]✅ Working[/green]" if proxy.is_working else "[red]❌ Failed[/red]"
                latency = f"{proxy.latency_ms}ms" if proxy.latency_ms else "N/A"
                total = proxy.success_count + proxy.fail_count
                rate = f"{(proxy.success_count / total * 100):.0f}%" if total > 0 else "N/A"
                
                table.add_row(
                    proxy.server[:40],
                    status,
                    latency,
                    str(proxy.success_count),
                    str(proxy.fail_count),
                    rate,
                    proxy.source or "manual"
                )
            
            self.console.print(table)
            
            return InspectionReport(
                success=True,
                timestamp=datetime.now(),
                data={
                    'total': len(proxies),
                    'working': len(working),
                    'failed': len(failed),
                    'avg_latency': avg_latency
                },
                warnings=[],
                errors=[]
            )
            
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return None
    
    # =========================================================================
    # SYSTEM INSPECTION
    # =========================================================================
    
    def inspect_system(self) -> Optional[InspectionReport]:
        """Full system inspection."""
        if not self.db_connected:
            self.console.print("[red]❌ Database not connected[/red]")
            return None
        
        try:
            # Gather all stats
            account_stats = self.db.get_account_stats()
            proxy_stats = self.db.get_proxy_stats()
            task_stats = self.db.get_task_stats(hours=24)
            
            system_info = f"""[bold cyan]🖥️ System Status[/bold cyan]

[bold]📊 Accounts:[/bold]
  Total: {account_stats['total']}
  Active: [green]{account_stats['active']}[/green]
  Banned: [red]{account_stats['banned']}[/red]
  Other: {account_stats['other']}
  Total Follows: {account_stats['total_follows']}

[bold]🌐 Proxies:[/bold]
  Total: {proxy_stats['total']}
  Working: [green]{proxy_stats['working']}[/green]
  Failed: [red]{proxy_stats['failed']}[/red]
  Avg Latency: {proxy_stats['avg_latency_ms'] or 'N/A'}ms

[bold]📋 Tasks (24h):[/bold]
  Total: {task_stats['total']}
  Success: [green]{task_stats['success']}[/green]
  Failed: [red]{task_stats['failed']}[/red]
  Success Rate: {task_stats['success_rate']}%

[bold]🔧 Environment:[/bold]
  Python: {sys.version.split()[0]}
  Database: ✅ Connected
"""
            
            self.console.print(Panel(system_info, title="🔍 Full System Inspection", border_style="cyan"))
            
            # Show recent errors
            errors = self.db.get_recent_errors(limit=5)
            if errors:
                error_table = Table(title="⚠️ Recent Errors", border_style="red")
                error_table.add_column("Time", style="dim", width=16)
                error_table.add_column("Type", width=15)
                error_table.add_column("Error", style="red")
                
                for err in errors:
                    error_table.add_row(
                        err.timestamp.strftime("%m/%d %H:%M"),
                        err.task_type,
                        (err.error_message[:50] + "...") 
                        if len(err.error_message or "") > 50 
                        else (err.error_message or "Unknown")
                    )
                
                self.console.print(error_table)
            
            return InspectionReport(
                success=True,
                timestamp=datetime.now(),
                data={
                    'accounts': account_stats,
                    'proxies': proxy_stats,
                    'tasks': task_stats
                },
                warnings=[],
                errors=[]
            )
            
        except Exception as e:
            self.console.print(f"[red]Error: {e}[/red]")
            return None


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

if __name__ == '__main__':
    from rich.console import Console
    
    console = Console()
    inspector = Inspector(console)
    
    console.print("[bold]🔍 Running full system inspection...[/bold]\n")
    inspector.inspect_system()
    console.print()
    inspector.inspect_all_accounts()
