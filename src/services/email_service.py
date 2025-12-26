"""
Email Service - Self-hosted email verification using Maddy.

Maddy is a self-hosted mail server that provides:
- Full SMTP/IMAP server
- Unlimited email addresses on your domain
- Complete control over email

Requirements:
- Domain name ($10/year)
- VPS server ($5/month)
- Docker

Usage:
    from src.services.email_service import EmailService
    
    service = EmailService("mail.yourdomain.com", "yourdomain.com")
    email = service.generate_address()  # random@yourdomain.com
    link = await service.wait_for_verification(email)
"""

import asyncio
import imaplib
import email
import random
import string
import re
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from email.header import decode_header
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Parsed email message."""
    subject: str
    sender: str
    body_text: str
    body_html: str
    date: datetime
    

class EmailService:
    """
    Self-hosted email service for account verification.
    
    Uses Maddy or any IMAP-compatible mail server.
    """
    
    def __init__(
        self,
        imap_server: str,
        domain: str,
        imap_port: int = 993,
        smtp_server: str = None,
        smtp_port: int = 587,
        username: str = None,
        password: str = None,
        use_ssl: bool = True
    ):
        self.imap_server = imap_server
        self.domain = domain
        self.imap_port = imap_port
        self.smtp_server = smtp_server or imap_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        
        # Track generated addresses
        self.generated_addresses: List[str] = []
    
    def generate_address(self, prefix: str = None) -> str:
        """
        Generate a unique email address on your domain.
        
        Args:
            prefix: Optional prefix for the address
            
        Returns:
            Email address string
        """
        if prefix:
            local_part = f"{prefix}_{self._random_string(6)}"
        else:
            local_part = self._random_string(10)
        
        address = f"{local_part}@{self.domain}"
        self.generated_addresses.append(address)
        
        return address
    
    def _random_string(self, length: int) -> str:
        """Generate random alphanumeric string."""
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choices(chars, k=length))
    
    async def connect(self) -> imaplib.IMAP4_SSL:
        """
        Connect to IMAP server.
        
        Returns:
            IMAP connection object
        """
        try:
            if self.use_ssl:
                mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            else:
                mail = imaplib.IMAP4(self.imap_server, self.imap_port)
            
            if self.username and self.password:
                mail.login(self.username, self.password)
            
            return mail
        
        except Exception as e:
            logger.error(f"Failed to connect to IMAP: {e}")
            raise
    
    async def wait_for_verification(
        self,
        email_address: str,
        from_filter: str = "roblox",
        timeout_seconds: int = 120,
        poll_interval: int = 5
    ) -> Optional[str]:
        """
        Wait for verification email and extract link.
        
        Args:
            email_address: Address to check
            from_filter: Filter emails from this sender
            timeout_seconds: Max time to wait
            poll_interval: Seconds between checks
            
        Returns:
            Verification link or None
        """
        logger.info(f"Waiting for verification email to {email_address}...")
        
        start_time = datetime.now()
        max_time = start_time + timedelta(seconds=timeout_seconds)
        
        while datetime.now() < max_time:
            try:
                link = await self._check_for_verification(email_address, from_filter)
                if link:
                    logger.info(f"✅ Found verification link!")
                    return link
            except Exception as e:
                logger.debug(f"Check failed: {e}")
            
            await asyncio.sleep(poll_interval)
        
        logger.warning(f"Timeout waiting for verification email")
        return None
    
    async def _check_for_verification(
        self,
        email_address: str,
        from_filter: str
    ) -> Optional[str]:
        """Check mailbox for verification email."""
        
        mail = await self.connect()
        
        try:
            mail.select("INBOX")
            
            # Search for emails from the filter
            search_criteria = f'(FROM "{from_filter}")'
            status, data = mail.search(None, search_criteria)
            
            if not data[0]:
                return None
            
            email_ids = data[0].split()
            
            # Check most recent emails first
            for email_id in reversed(email_ids[-10:]):
                status, msg_data = mail.fetch(email_id, "(RFC822)")
                
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        msg = email.message_from_bytes(response_part[1])
                        
                        # Parse message
                        parsed = self._parse_message(msg)
                        
                        # Look for verification link
                        link = self._extract_verification_link(
                            parsed.body_html or parsed.body_text
                        )
                        
                        if link:
                            return link
            
            return None
        
        finally:
            mail.logout()
    
    def _parse_message(self, msg) -> EmailMessage:
        """Parse email message."""
        subject = ""
        subject_header = msg.get("Subject", "")
        if subject_header:
            decoded = decode_header(subject_header)
            subject = decoded[0][0]
            if isinstance(subject, bytes):
                subject = subject.decode()
        
        sender = msg.get("From", "")
        
        body_text = ""
        body_html = ""
        
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                try:
                    payload = part.get_payload(decode=True)
                    if payload:
                        text = payload.decode('utf-8', errors='ignore')
                        if content_type == "text/plain":
                            body_text = text
                        elif content_type == "text/html":
                            body_html = text
                except:
                    pass
        else:
            payload = msg.get_payload(decode=True)
            if payload:
                body_text = payload.decode('utf-8', errors='ignore')
        
        return EmailMessage(
            subject=subject,
            sender=sender,
            body_text=body_text,
            body_html=body_html,
            date=datetime.now()
        )
    
    def _extract_verification_link(self, content: str) -> Optional[str]:
        """Extract verification link from email content."""
        if not content:
            return None
        
        # Common Roblox verification patterns
        patterns = [
            r'https://www\.roblox\.com/[^\s"\'<>]+verify[^\s"\'<>]*',
            r'https://www\.roblox\.com/[^\s"\'<>]+confirm[^\s"\'<>]*',
            r'https://www\.roblox\.com/Login/Verify\.ashx\?[^\s"\'<>]+',
            r'href=["\']([^"\']*roblox\.com[^"\']*verify[^"\']*)["\']',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                link = matches[0]
                # Clean up the link
                link = link.replace('&amp;', '&')
                return link
        
        return None
    
    async def get_recent_messages(
        self,
        limit: int = 10,
        from_filter: str = None
    ) -> List[EmailMessage]:
        """Get recent messages from inbox."""
        mail = await self.connect()
        messages = []
        
        try:
            mail.select("INBOX")
            
            if from_filter:
                status, data = mail.search(None, f'(FROM "{from_filter}")')
            else:
                status, data = mail.search(None, "ALL")
            
            if data[0]:
                email_ids = data[0].split()
                
                for email_id in reversed(email_ids[-limit:]):
                    status, msg_data = mail.fetch(email_id, "(RFC822)")
                    
                    for response_part in msg_data:
                        if isinstance(response_part, tuple):
                            msg = email.message_from_bytes(response_part[1])
                            messages.append(self._parse_message(msg))
        
        finally:
            mail.logout()
        
        return messages


# ============== Docker Compose Template ==============

MADDY_DOCKER_COMPOSE = """
version: '3.8'

services:
  maddy:
    image: foxcpp/maddy:latest
    container_name: roblox-mail-server
    hostname: {hostname}
    environment:
      - MADDY_HOSTNAME={hostname}
      - MADDY_DOMAIN={domain}
    ports:
      # SMTP
      - "25:25"
      - "465:465"
      - "587:587"
      # IMAP
      - "993:993"
      - "143:143"
    volumes:
      - ./maddy_data:/data
      - ./maddy_config:/etc/maddy
    restart: unless-stopped

# DNS Records Required:
# A record: mail.{domain} -> YOUR_SERVER_IP
# MX record: @ -> mail.{domain} (priority 10)
# TXT record (SPF): @ -> "v=spf1 mx ~all"
# TXT record (DKIM): Will be generated by Maddy
"""


def generate_docker_compose(domain: str, output_path: str = None) -> str:
    """
    Generate Docker Compose file for Maddy.
    
    Args:
        domain: Your domain name
        output_path: Where to save the file
        
    Returns:
        Docker compose content
    """
    hostname = f"mail.{domain}"
    content = MADDY_DOCKER_COMPOSE.format(
        hostname=hostname,
        domain=domain
    )
    
    if output_path:
        with open(output_path, 'w') as f:
            f.write(content)
        logger.info(f"Docker compose saved to {output_path}")
    
    return content


# ============== Setup Instructions ==============

SETUP_INSTRUCTIONS = """
# Maddy Email Server Setup Guide

## Prerequisites
1. Domain name (e.g., my-roblox-bot.com) - ~$10/year
2. VPS server (DigitalOcean, Vultr, Hetzner) - ~$5/month
3. Docker installed on VPS

## Step 1: DNS Configuration

Add these DNS records:

| Type | Name | Value |
|------|------|-------|
| A | mail | YOUR_VPS_IP |
| MX | @ | mail.yourdomain.com (priority 10) |
| TXT | @ | v=spf1 mx ~all |

## Step 2: Deploy Maddy

```bash
# On your VPS:
mkdir -p /opt/maddy
cd /opt/maddy

# Create docker-compose.yml (use generate_docker_compose function)

# Start Maddy
docker-compose up -d

# Check logs
docker logs -f roblox-mail-server
```

## Step 3: Configure Your Bot

```python
from src.services.email_service import EmailService

# Initialize service
email_service = EmailService(
    imap_server="mail.yourdomain.com",
    domain="yourdomain.com",
    username="admin@yourdomain.com",  # Optional
    password="your_password"           # Optional
)

# Generate email for new account
email = email_service.generate_address("roblox")
# Result: roblox_abc123@yourdomain.com

# Use email in account creation
# ...

# Wait for verification
link = await email_service.wait_for_verification(email)
if link:
    # Navigate to link with Playwright
    await page.goto(link)
```

## Troubleshooting

1. **Emails not arriving?**
   - Check MX record is correct
   - Verify port 25 is open
   - Check Maddy logs

2. **SPF/DKIM issues?**
   - Add required TXT records
   - Wait for DNS propagation (can take hours)

3. **Connection refused?**
   - Ensure firewall allows ports 993, 587, 25
   - Verify Maddy is running
"""


def print_setup_instructions():
    """Print setup instructions."""
    print(SETUP_INSTRUCTIONS)


if __name__ == "__main__":
    print_setup_instructions()

