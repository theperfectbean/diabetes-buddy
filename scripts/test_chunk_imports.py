import logging
logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(message)s')
logger = logging.getLogger(__name__)

logger.info("Importing tiktoken...")
import tiktoken
logger.info("✓ tiktoken")

logger.info("Importing os...")
import os
logger.info("✓ os")

logger.info("Importing json...")
import json
logger.info("✓ json")

logger.info("Importing argparse...")
import argparse
logger.info("✓ argparse")

logger.info("Importing pathlib...")
from pathlib import Path
logger.info("✓ pathlib")

logger.info("Importing datetime...")
from datetime import datetime, timezone
logger.info("✓ datetime")

logger.info("Importing time...")
import time
logger.info("✓ time")

logger.info("Importing gc...")
import gc
logger.info("✓ gc")

logger.info("All imports successful!")

logger.info("Testing tiktoken encoding...")
enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
logger.info("✓ Encoding loaded")