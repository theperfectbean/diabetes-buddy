import tiktoken
import logging
logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(message)s')

logger = logging.getLogger(__name__)
logger.info("Loading tiktoken encoding...")
enc = tiktoken.encoding_for_model("gpt-3.5-turbo")
logger.info("Encoding loaded!")

text = open('data/sources/openaps-docs/docs/api/index.rst').read()
logger.info(f"File read: {len(text)} chars")

logger.info("Encoding text...")
tokens = enc.encode(text)
logger.info(f"Encoded: {len(tokens)} tokens")