"""
Free Email Service - Zero-cost temporary email APIs.

Uses FREE APIs:
- 1secmail.com - Unlimited temp emails
- Mail.tm - Unlimited temp emails

NO VPS, NO Domain, NO Cost!

Usage:
    from src.services.free_email import FreeEmailService
    
    email = FreeEmailService()
    address = await email.create_inbox()  # abc123@1secmail.com
    link = await email.wait_for_verification(address, from_filter="roblox")
"""

import asyncio
import aiohttp
import random
import string
import re
import logging
from typing import Optional, List, Dict
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Parsed email message."""
    id: str
    sender: str
    subject: str
    body: str
    date: str


class OneSecMailAPI:
    """
    1secmail.com API - Free temporary email.
    
    API Docs: https://www.1secmail.com/api/
    Limits: Unlimited, no registration required
    """
    
    BASE_URL = "https://www.1secmail.com/api/v1/"
    DOMAINS = ["1secmail.com", "1secmail.org", "1secmail.net"]
    
    def __init__(self):
        self.current_address: Optional[str] = None
        self.login: Optional[str] = None
        self.domain: Optional[str] = None
    
    async def generate_address(self) -> str:
        """Generate a random email address."""
        self.login = self._random_string(10)
        self.domain = random.choice(self.DOMAINS)
        self.current_address = f"{self.login}@{self.domain}"
        logger.info(f"📧 Generated: {self.current_address}")
        return self.current_address
    
    async def get_messages(self) -> List[Dict]:
        """Get all messages in inbox."""
        if not self.login or not self.domain:
            return []
        
        url = f"{self.BASE_URL}?action=getMessages&login={self.login}&domain={self.domain}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
            except Exception as e:
                logger.debug(f"Get messages failed: {e}")
        
        return []
    
    async def read_message(self, message_id: int) -> Optional[Dict]:
        """Read a specific message."""
        if not self.login or not self.domain:
            return None
        
        url = f"{self.BASE_URL}?action=readMessage&login={self.login}&domain={self.domain}&id={message_id}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        return await response.json()
            except Exception as e:
                logger.debug(f"Read message failed: {e}")
        
        return None
    
    async def wait_for_email(
        self,
        from_filter: str = None,
        subject_filter: str = None,
        timeout: int = 120,
        poll_interval: int = 5
    ) -> Optional[Dict]:
        """Wait for an email matching filters."""
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            messages = await self.get_messages()
            
            for msg in messages:
                # Check filters
                if from_filter and from_filter.lower() not in msg.get('from', '').lower():
                    continue
                if subject_filter and subject_filter.lower() not in msg.get('subject', '').lower():
                    continue
                
                # Found matching message
                full_msg = await self.read_message(msg['id'])
                if full_msg:
                    return full_msg
            
            await asyncio.sleep(poll_interval)
        
        return None
    
    def _random_string(self, length: int) -> str:
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choices(chars, k=length))


class MailTmAPI:
    """
    Mail.tm API - Free temporary email.
    
    API Docs: https://docs.mail.tm/
    Limits: Unlimited, requires account creation
    """
    
    BASE_URL = "https://api.mail.tm"
    
    def __init__(self):
        self.token: Optional[str] = None
        self.account_id: Optional[str] = None
        self.address: Optional[str] = None
    
    async def create_account(self) -> str:
        """Create a new email account."""
        async with aiohttp.ClientSession() as session:
            # Get available domain
            async with session.get(f"{self.BASE_URL}/domains", timeout=10) as resp:
                domains_data = await resp.json()
                if not domains_data.get('hydra:member'):
                    raise Exception("No domains available")
                domain = domains_data['hydra:member'][0]['domain']
            
            # Create account
            username = self._random_string(10)
            password = self._random_string(12)
            self.address = f"{username}@{domain}"
            
            payload = {
                "address": self.address,
                "password": password
            }
            
            async with session.post(
                f"{self.BASE_URL}/accounts",
                json=payload,
                timeout=10
            ) as resp:
                if resp.status in [200, 201]:
                    data = await resp.json()
                    self.account_id = data['id']
            
            # Login to get token
            async with session.post(
                f"{self.BASE_URL}/token",
                json={"address": self.address, "password": password},
                timeout=10
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self.token = data['token']
        
        logger.info(f"📧 Created: {self.address}")
        return self.address
    
    async def get_messages(self) -> List[Dict]:
        """Get all messages."""
        if not self.token:
            return []
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self.BASE_URL}/messages",
                    headers=headers,
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('hydra:member', [])
            except Exception as e:
                logger.debug(f"Get messages failed: {e}")
        
        return []
    
    async def read_message(self, message_id: str) -> Optional[Dict]:
        """Read a specific message."""
        if not self.token:
            return None
        
        headers = {"Authorization": f"Bearer {self.token}"}
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(
                    f"{self.BASE_URL}/messages/{message_id}",
                    headers=headers,
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
            except Exception as e:
                logger.debug(f"Read message failed: {e}")
        
        return None
    
    async def wait_for_email(
        self,
        from_filter: str = None,
        timeout: int = 120,
        poll_interval: int = 5
    ) -> Optional[Dict]:
        """Wait for an email matching filters."""
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            messages = await self.get_messages()
            
            for msg in messages:
                if from_filter:
                    sender = msg.get('from', {}).get('address', '')
                    if from_filter.lower() not in sender.lower():
                        continue
                
                full_msg = await self.read_message(msg['id'])
                if full_msg:
                    return full_msg
            
            await asyncio.sleep(poll_interval)
        
        return None
    
    def _random_string(self, length: int) -> str:
        chars = string.ascii_lowercase + string.digits
        return ''.join(random.choices(chars, k=length))


class FreeEmailService:
    """
    Unified free email service.
    
    Tries multiple providers for reliability.
    """
    
    def __init__(self, provider: str = "1secmail"):
        """
        Initialize free email service.
        
        Args:
            provider: "1secmail" or "mailtm"
        """
        self.provider = provider
        
        if provider == "1secmail":
            self._api = OneSecMailAPI()
        else:
            self._api = MailTmAPI()
        
        self.current_address: Optional[str] = None
    
    async def create_inbox(self) -> str:
        """
        Create a new email inbox.
        
        Returns:
            Email address
        """
        if self.provider == "1secmail":
            self.current_address = await self._api.generate_address()
        else:
            self.current_address = await self._api.create_account()
        
        return self.current_address
    
    async def wait_for_verification(
        self,
        email: str = None,
        from_filter: str = "roblox",
        timeout: int = 120
    ) -> Optional[str]:
        """
        Wait for verification email and extract link.
        
        Args:
            email: Email address (uses current if not provided)
            from_filter: Filter sender (default: roblox)
            timeout: Max wait time
            
        Returns:
            Verification link or None
        """
        logger.info(f"⏳ Waiting for verification email...")
        
        msg = await self._api.wait_for_email(
            from_filter=from_filter,
            timeout=timeout
        )
        
        if not msg:
            logger.warning("❌ No verification email received")
            return None
        
        # Extract link from message body
        body = msg.get('body', '') or msg.get('text', '') or msg.get('htmlBody', '')
        link = self._extract_verification_link(body)
        
        if link:
            logger.info(f"✅ Found verification link!")
            return link
        
        logger.warning("❌ No verification link found in email")
        return None
    
    def _extract_verification_link(self, content: str) -> Optional[str]:
        """Extract Roblox verification link from email content."""
        if not content:
            return None
        
        patterns = [
            r'https://www\.roblox\.com/[^\s"\'<>]+verify[^\s"\'<>]*',
            r'https://www\.roblox\.com/[^\s"\'<>]+confirm[^\s"\'<>]*',
            r'https://www\.roblox\.com/Login/Verify\.ashx\?[^\s"\'<>]+',
            r'href=["\']([^"\']*roblox\.com[^"\']*verify[^"\']*)["\']',
            r'https://www\.roblox\.com/[^\s"\'<>]+email-verification[^\s"\'<>]*',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                link = matches[0]
                link = link.replace('&amp;', '&')
                return link
        
        return None
    
    async def get_messages(self) -> List[Dict]:
        """Get all messages in inbox."""
        return await self._api.get_messages()


# ============== Convenience Functions ==============

async def create_verified_email() -> tuple:
    """
    Create a new email and wait for it to be ready.
    
    Returns:
        (email_address, email_service)
    """
    service = FreeEmailService("1secmail")
    address = await service.create_inbox()
    return address, service


async def test_email_service():
    """Test the email service."""
    print("Testing 1secmail API...")
    
    api = OneSecMailAPI()
    address = await api.generate_address()
    print(f"Generated: {address}")
    
    messages = await api.get_messages()
    print(f"Messages: {len(messages)}")
    
    print("\n✅ Email service working!")
    return address


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(test_email_service())

