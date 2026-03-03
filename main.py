import asyncio
import random
import base64
import os
import json
from datetime import datetime
import indian_names
from faker import Faker
from playwright.async_api import async_playwright
import nest_asyncio
import firebase_admin
from firebase_admin import credentials, db

nest_asyncio.apply()

# Railway se Firebase creds
firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
cred_dict = json.loads(firebase_creds_json)
cred = credentials.Certificate(cred_dict)
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://zoom-bot-controller-default-rtdb.asia-southeast1.firebasedatabase.app/'
})

INSTANCE_ID = f"railway_{os.environ.get('RAILWAY_SERVICE_ID', 'unknown')[:4]}_{random.randint(100,999)}"
fake = Faker('en_US')

def get_name(name_mode="indian"):
    if name_mode == "english":
        gender = random.choice(['male', 'female'])
        return (fake.first_name_male() if gender == 'male' else fake.first_name_female()) + " " + fake.last_name()
    else:
        return indian_names.get_full_name(gender=random.choice(['male', 'female']))

class ZoomBot:
    def __init__(self, instance_id, bot_id, meeting_code, passcode, duration, name_mode="indian"):
        self.instance_id = instance_id
        self.bot_id = bot_id
        self.meeting_code = meeting_code
        self.passcode = passcode
        self.duration = duration
        self.name_mode = name_mode
        self.tag = f"[{instance_id} | Bot {bot_id}]"
        
    async def run(self):
        print(f"{self.tag} Starting...")
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, args=['--no-sandbox'])
            page = await browser.new_page()
            
            domain = base64.b64decode('em9vbS51cw==').decode()
            await page.goto(f"https://{domain}/wc/join/{self.meeting_code}")
            
            # Name
            await page.locator('xpath=//*[@id="input-for-name"]').fill(get_name(self.name_mode))
            
            # Passcode
            if self.passcode and self.passcode != "skip":
                await page.locator('xpath=//input[@type="password"]').fill(self.passcode)
            
            # Wait for start signal
            while db.reference('commands/global/start_signal').get() != "go":
                await asyncio.sleep(1)
            
            # Join
            await page.locator('xpath=//button[contains(text(), "Join")]').click()
            
            # Wait in meeting
            await asyncio.sleep(self.duration * 60)
            await browser.close()

class RailwayWorker:
    def __init__(self):
        self.instance_id = INSTANCE_ID
        self.bots_running = 0
        
    async def heartbeat(self):
        ref = db.reference(f'instances/{self.instance_id}')
        while True:
            await ref.set({
                'id': self.instance_id,
                'status': 'busy' if self.bots_running > 0 else 'idle',
                'last_heartbeat': datetime.now().isoformat(),
                'bots_capacity': 5,
                'name_mode': 'indian'
            })
            await asyncio.sleep(5)
    
    async def listen(self):
        ref = db.reference(f'commands/{self.instance_id}')
        while True:
            cmd = await ref.get()
            if cmd and cmd.get('action') == 'start_bots':
                print(f"📥 Received: {cmd}")
                tasks = []
                for i in range(cmd['count']):
                    bot = ZoomBot(
                        self.instance_id, 
                        f"bot_{i}", 
                        cmd['meeting'], 
                        cmd.get('passcode', 'skip'), 
                        cmd.get('duration', 90),
                        cmd.get('name_mode', 'indian')
                    )
                    tasks.append(bot.run())
                    self.bots_running += 1
                await asyncio.gather(*tasks, return_exceptions=True)
                self.bots_running = 0
            await asyncio.sleep(2)
    
    async def run(self):
        print(f"🚀 Railway Worker: {self.instance_id}")
        asyncio.create_task(self.heartbeat())
        await self.listen()

if __name__ == "__main__":
    worker = RailwayWorker()
    asyncio.run(worker.run())