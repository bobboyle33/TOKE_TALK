import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from torch import cosine_similarity
from web3 import Web3
import json
import asyncio
import requests
from web3.exceptions import ContractLogicError
import web3
from bs4 import BeautifulSoup
import matplotlib.pyplot as plt
from io import BytesIO
import time
from decimal import Decimal
import textwrap
import binascii
import aiohttp
from datetime import datetime, timedelta
import io
from matplotlib import font_manager
import numpy as np
import random
import colorsys
from PIL import Image
from collections import Counter, defaultdict
import matplotlib.animation as animation
import imageio
from matplotlib.animation import FFMpegWriter
from matplotlib.colors import LinearSegmentedColormap
import openai
import math
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from dotenv import load_dotenv

import sys
import os

print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")
print(f"sys.path: {sys.path}")

try:
    import sklearn
    print(f"sklearn version: {sklearn.__version__}")
except ImportError as e:
    print(f"Error importing sklearn: {e}")

# Add this line near the top of your file to print the Web3.py version
print(f"Web3.py version: {web3.__version__}")

# Set up logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Telegram bot
TOKEN = '7656983535:AAGy1a8yGXS6IeyN12nX4uyw4aR1EBQfqX0'

# Initialize Web3 connection to Infura
INFURA_KEY = '12f83e3966314e5bad031d3d968f3ac3'
INFURA_URL = f'https://mainnet.infura.io/v3/{INFURA_KEY}'
w3 = Web3(Web3.HTTPProvider(INFURA_URL))

# Define the GITBOOK_URL here
GITBOOK_URL = "https://docs.tokemak.xyz/"
MAX_MESSAGE_LENGTH = 4096

# Check Web3 connection
if not w3.is_connected():
    logger.error("Failed to connect to Ethereum network")
    raise Exception("Web3 connection failed")

# Contract addresses
VAULT_CONTRACT_ADDRESS = '0x0A2b94F6871c1D7A32Fe58E1ab5e6deA2f114E56'
STAKING_CONTRACT_ADDRESS = '0x2218F90A98b0C070676f249EF44834686dAa4285'

# Load ABIs from files
script_dir = os.path.dirname(os.path.abspath(__file__))
vault_abi_path = os.path.join(script_dir, 'vault_abi.json')
staking_abi_path = os.path.join(script_dir, 'staking_abi.json')

try:
    with open(vault_abi_path, 'r') as f:
        VAULT_ABI = json.load(f)
except FileNotFoundError:
    logger.error(f"Vault ABI file not found at {vault_abi_path}")
    raise

try:
    with open(staking_abi_path, 'r') as f:
        STAKING_ABI = json.load(f)
except FileNotFoundError:
    logger.error(f"Staking ABI file not found at {staking_abi_path}")
    raise

# Create contract instances
vault_contract = w3.eth.contract(address=VAULT_CONTRACT_ADDRESS, abi=VAULT_ABI)
staking_contract = w3.eth.contract(address=STAKING_CONTRACT_ADDRESS, abi=STAKING_ABI)

# Add these new constants
BLOCKS_PER_YEAR = 2300000  # Approximate number of blocks per year on Ethereum
REWARD_TOKEN_ADDRESS = '0x2e9d63788249371f1DFC918a52f8d799F4a38C94'
STAKING_TOKEN_ADDRESS = '0x0A2b94F6871c1D7A32Fe58E1ab5e6deA2f114E56'

# Add this near the top of your file
ETHERSCAN_API_KEY = "I58RNAZ5C2PPCCQ8YG38ECNPD4GZSRA1FN"

# Pool addresses
BALETH_ADDRESS = '0x0A2b94F6871c1D7A32Fe58E1ab5e6deA2f114E56'
AUTOLRT_ADDRESS = '0x0A2b94F6871c1D7A32Fe58E1ab5e6deA2f114E56'  # Replace with actual autoLRT address

# ABI for the functions we need
ABI = [
    {"inputs":[],"name":"totalSupply","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"totalAssets","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"},
    {"inputs":[],"name":"getDestinations","outputs":[{"internalType":"address[]","name":"","type":"address[]"}],"stateMutability":"view","type":"function"},
    {"inputs":[{"internalType":"address","name":"destination","type":"address"}],"name":"getDestinationInfo","outputs":[{"components":[{"internalType":"uint248","name":"currentBalance","type":"uint248"},{"internalType":"uint8","name":"currentAllocation","type":"uint8"}],"internalType":"struct LMPVault.DestinationInfo","name":"","type":"tuple"}],"stateMutability":"view","type":"function"}
]

# Pool addresses
POOLS = {
    'autoETH': '0x0A2b94F6871c1D7A32Fe58E1ab5e6deA2f114E56',
    'autoLRT': '0xe800e3760fc20aa98c5df6a9816147f190455af3',
    'balETH': '0x6dC3ce9C57b20131347FDc9089D740DAf6eB34c5'
}

# Convert addresses to checksum format
POOLS = {
    name: Web3.to_checksum_address(address) 
    for name, address in POOLS.items()
}

# Define the pool IDs you're looking for and their corresponding names
pool_ids = {
    '5a9c2073-2190-4002-9654-8c245d1e8534': 'balETH',
    'e9a686bf-21ed-4f78-82be-cd32625c4725': 'autoETH',
    '06a77517-529a-465e-8157-ba752207676b': 'autoLRT'
}

async def get_token_price(token_address):
    url = f"https://api.coingecko.com/api/v3/simple/token_price/ethereum?contract_addresses={token_address}&vs_currencies=usd"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data[token_address.lower()]['usd']
    else:
        return None

async def calculate_apr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        logger.info("Starting APR calculation")
        
        # Get reward rate from staking contract
        logger.info("Attempting to call rewardRate()")
        try:
            reward_rate = staking_contract.functions.rewardRate().call()
            logger.info(f"Reward rate: {reward_rate}")
        except Exception as e:
            logger.error(f"Error calling rewardRate(): {str(e)}")
            reward_rate = None

        # Get total supply (total staked) from staking contract
        logger.info("Attempting to call totalSupply()")
        try:
            total_supply = staking_contract.functions.totalSupply().call()
            logger.info(f"Total supply: {total_supply}")
        except Exception as e:
            logger.error(f"Error calling totalSupply(): {str(e)}")
            total_supply = None

        # If we couldn't get the basic contract data, stop here
        if reward_rate is None or total_supply is None:
            logger.error("Failed to retrieve basic contract data")
            await update.message.reply_text("Unable to retrieve basic contract data. Please try again later.")
            return

        # Get token prices
        logger.info("Fetching token prices")
        reward_token_price = await get_token_price(REWARD_TOKEN_ADDRESS)
        staking_token_price = await get_token_price(STAKING_TOKEN_ADDRESS)
        logger.info(f"Reward token price: {reward_token_price}, Staking token price: {staking_token_price}")

        if reward_token_price is None or staking_token_price is None:
            logger.error("Failed to fetch token prices")
            await update.message.reply_text("Unable to fetch token prices. Please try again later.")
            return

        # Calculate APR
        annual_rewards = reward_rate * BLOCKS_PER_YEAR
        annual_rewards_value = annual_rewards * reward_token_price
        total_staked_value = total_supply * staking_token_price

        apr = (annual_rewards_value / total_staked_value) * 100

        logger.info(f"Calculated APR: {apr}")

        message = f"Estimated APR: {apr:.2f}%\n"
        message += f"Reward Rate: {Web3.from_wei(reward_rate, 'ether')} tokens per block\n"
        message += f"Total Staked: {Web3.from_wei(total_supply, 'ether')} tokens\n"
        message += f"Reward Token Price: ${reward_token_price:.2f}\n"
        message += f"Staking Token Price: ${staking_token_price:.2f}"

        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error in calculate_apr: {str(e)}")
        logger.exception("Full traceback:")
        await update.message.reply_text(f"An error occurred while calculating APR: {str(e)}")

async def get_pool_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        logger.info("Attempting to get pool info")
        
        try:
            total_assets = vault_contract.functions.totalAssets().call()
            logger.info(f"Total assets: {total_assets}")
        except Exception as e:
            logger.error(f"Error getting total assets: {str(e)}")
            total_assets = None
        
        try:
            fee_settings = vault_contract.functions.getFeeSettings().call()
            logger.info(f"Fee settings: {fee_settings}")
        except Exception as e:
            logger.error(f"Error getting fee settings: {str(e)}")
            fee_settings = None
        
        try:
            asset_breakdown = vault_contract.functions.getAssetBreakdown().call()
            logger.info(f"Asset breakdown: {asset_breakdown}")
        except Exception as e:
            logger.error(f"Error getting asset breakdown: {str(e)}")
            asset_breakdown = None
        
        if total_assets is None and fee_settings is None and asset_breakdown is None:
            await update.message.reply_text("Unable to retrieve any pool information. Please try again later.")
            return
        
        message = "Pool Information:\n"
        if total_assets is not None:
            message += f"Total Assets: {Web3.from_wei(total_assets, 'ether')} ETH\n"
        if fee_settings is not None:
            message += f"Fee Settings: {fee_settings}\n"
        if asset_breakdown is not None:
            message += f"Idle Assets: {Web3.from_wei(asset_breakdown[0], 'ether')} ETH\n"
            message += f"Debt Assets: {Web3.from_wei(asset_breakdown[1], 'ether')} ETH\n"
        
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error in get_pool_info: {str(e)}")
        logger.exception("Full traceback:")
        await update.message.reply_text(f"An error occurred while getting pool info: {str(e)}")

async def get_pool_apr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Get fee settings
        fee_settings = vault_contract.functions.getFeeSettings().call()
        streaming_fee_bps = fee_settings[6]
        
        # Convert basis points to APR percentage
        apr_percentage = streaming_fee_bps / 100

        # Construct message
        message = f"Current Pool APR: {apr_percentage:.2f}%"

        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error in get_pool_apr: {str(e)}")
        await update.message.reply_text(f"An error occurred: {str(e)}")

async def get_vault_assets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Get total assets
        total_assets = vault_contract.functions.totalAssets().call()
        
        # Get breakdown of assets
        asset_breakdown = vault_contract.functions.getAssetBreakdown().call()
        idle_assets = asset_breakdown[0]
        debt_assets = asset_breakdown[1]
        
        # Convert Wei to ETH
        total_eth = w3.from_wei(total_assets, 'ether')
        idle_eth = w3.from_wei(idle_assets, 'ether')
        debt_eth = w3.from_wei(debt_assets, 'ether')
        
        # Construct message
        message = "Vault Assets Breakdown:\n"
        message += f"Total Assets: {total_eth:.4f} ETH\n"
        message += f"Idle Assets: {idle_eth:.4f} ETH\n"
        message += f"Debt Assets: {debt_eth:.4f} ETH"
        
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error in get_vault_assets: {str(e)}")
        await update.message.reply_text(f"An error occurred: {str(e)}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_message = (
        "Welcome to the Tokemak Info Bot!\n\n"
        "Available commands:\n"
        "/autoETH - Get metrics for the autoETH pool\n"
        "/autoLRT - Get metrics for the autoLRT pool\n"
        "/balETH - Get metrics for the balETH pool\n"
        "/tokemaktvl - View Tokemak's Total Value Locked (TVL) over time\n"
        "/poolsummary - Get a summary of all pools\n"
        "/gitbook - Access Tokemak's GitBook documentation\n"
        "/ask <question> - Ask a question about Tokemak\n"
        "/help - Show this help message"
    )
    await update.message.reply_text(welcome_message)

# Add this new function
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)  # Reuse the start command for help

async def rebalance_notification(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Get current assets
        current_assets = vault_contract.functions.totalAssets().call()
        asset_breakdown = vault_contract.functions.getAssetBreakdown().call()
        current_idle = asset_breakdown[0]
        current_debt = asset_breakdown[1]

        # Compare with previous assets
        previous_assets = context.bot_data.get('previous_assets', (0, 0, 0))

        if (current_assets, current_idle, current_debt) != previous_assets:
            # Assets have changed, send notification
            message = "Rebalance Alert: Assets in the pools have been rebalanced.\n\n"
            message += "New Asset Breakdown:\n"
            message += f"Total Assets: {w3.from_wei(current_assets, 'ether'):.4f} ETH\n"
            message += f"Idle Assets: {w3.from_wei(current_idle, 'ether'):.4f} ETH\n"
            message += f"Debt Assets: {w3.from_wei(current_debt, 'ether'):.4f} ETH"

            # Send message to all subscribed users
            for user_id in context.bot_data.get('subscribed_users', set()):
                await context.bot.send_message(chat_id=user_id, text=message)

            # Update previous assets
            context.bot_data['previous_assets'] = (current_assets, current_idle, current_debt)

    except Exception as e:
        logger.error(f"Error in rebalance notification: {str(e)}")

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if 'subscribed_users' not in context.bot_data:
        context.bot_data['subscribed_users'] = set()
    context.bot_data['subscribed_users'].add(user_id)
    await update.message.reply_text("You have been subscribed to rebalance notifications.")

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if 'subscribed_users' in context.bot_data:
        context.bot_data['subscribed_users'].discard(user_id)
    await update.message.reply_text("You have been unsubscribed from rebalance notifications.")

async def check_contract_abi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        functions = [func['name'] for func in STAKING_ABI if func['type'] == 'function']
        message = "Available functions in the staking contract:\n" + "\n".join(functions)
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error checking contract ABI: {str(e)}")
        await update.message.reply_text(f"Error checking contract ABI: {str(e)}")

# Add this after initializing Web3
async def check_network(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        network = w3.eth.chain_id
        latest_block = w3.eth.get_block('latest')
        message = f"Connected to network with chain ID: {network}\n"
        message += f"Latest block number: {latest_block['number']}"
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error checking network: {str(e)}")
        await update.message.reply_text(f"Error checking network: {str(e)}")

async def check_web3_connection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if w3.is_connected():
            network = w3.eth.chain_id
            latest_block = w3.eth.get_block('latest')
            message = f"Connected to Ethereum network.\n"
            message += f"Chain ID: {network}\n"
            message += f"Latest block number: {latest_block['number']}"
        else:
            message = "Not connected to Ethereum network."
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error checking Web3 connection: {str(e)}")
        await update.message.reply_text(f"Error checking Web3 connection: {str(e)}")

async def check_contracts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        message = f"Vault Contract Address: {VAULT_CONTRACT_ADDRESS}\n"
        message += f"Staking Contract Address: {STAKING_CONTRACT_ADDRESS}\n\n"
        
        message += "Vault Contract Functions:\n"
        vault_functions = [func['name'] for func in VAULT_ABI if func['type'] == 'function']
        message += "\n".join(vault_functions[:10]) + "\n...\n\n"
        
        message += "Staking Contract Functions:\n"
        staking_functions = [func['name'] for func in STAKING_ABI if func['type'] == 'function']
        message += "\n".join(staking_functions[:10]) + "\n..."
        
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error checking contracts: {str(e)}")
        await update.message.reply_text(f"Error checking contracts: {str(e)}")

async def test_contract_read(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        message = "Testing contract read operations:\n\n"
        
        # Test vault contract
        try:
            vault_name = vault_contract.functions.name().call()
            message += f"Vault Contract Name: {vault_name}\n"
        except Exception as e:
            message += f"Error reading from vault contract: {str(e)}\n"
        
        # Test staking contract
        try:
            staking_name = staking_contract.functions.name().call()
            message += f"Staking Contract Name: {staking_name}\n"
        except Exception as e:
            message += f"Error reading from staking contract: {str(e)}\n"
        
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error in test_contract_read: {str(e)}")
        await update.message.reply_text(f"Error testing contract read: {str(e)}")

async def check_contract_existence(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        bytecode = w3.eth.get_code(STAKING_CONTRACT_ADDRESS)
        if bytecode == '0x':
            await update.message.reply_text("No contract found at the specified address.")
        else:
            await update.message.reply_text("Contract exists at the specified address.")
    except Exception as e:
        logger.error(f"Error checking contract existence: {str(e)}")
        await update.message.reply_text(f"Error checking contract existence: {str(e)}")

async def check_contract_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if 'owner' in [func['name'] for func in STAKING_ABI if func['type'] == 'function']:
            owner = staking_contract.functions.owner().call()
            await update.message.reply_text(f"Contract owner: {owner}")
        else:
            await update.message.reply_text("Contract does not have an 'owner' function")
    except Exception as e:
        logger.error(f"Error checking contract owner: {str(e)}")
        await update.message.reply_text(f"Error checking contract owner: {str(e)}")

async def list_contract_functions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        functions = [func['name'] for func in STAKING_ABI if func['type'] == 'function']
        message = "Available functions in the staking contract:\n" + "\n".join(functions)
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error listing contract functions: {str(e)}")
        await update.message.reply_text(f"Error listing contract functions: {str(e)}")

async def check_view_function(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        view_functions = [func['name'] for func in STAKING_ABI if func['type'] == 'function' and func['stateMutability'] == 'view']
        if view_functions:
            function_name = view_functions[0]
            result = getattr(staking_contract.functions, function_name)().call()
            await update.message.reply_text(f"{function_name}() result: {result}")
        else:
            await update.message.reply_text("No view functions found in the contract ABI.")
    except Exception as e:
        logger.error(f"Error checking view function: {str(e)}")
        await update.message.reply_text(f"Error checking view function: {str(e)}")

async def check_paused(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if 'paused' in [func['name'] for func in STAKING_ABI if func['type'] == 'function']:
            paused = staking_contract.functions.paused().call()
            await update.message.reply_text(f"Contract paused: {paused}")
        else:
            await update.message.reply_text("Contract does not have a 'paused' function")
    except Exception as e:
        await update.message.reply_text(f"Error checking paused status: {str(e)}")

async def check_total_supply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        total_supply = staking_contract.functions.totalSupply().call()
        await update.message.reply_text(f"Total Supply: {Web3.from_wei(total_supply, 'ether')} tokens")
    except Exception as e:
        logger.error(f"Error checking total supply: {str(e)}")
        await update.message.reply_text(f"Error checking total supply: {str(e)}")

async def check_owner(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if 'owner' in [func['name'] for func in STAKING_ABI if func['type'] == 'function']:
            owner = staking_contract.functions.owner().call()
            await update.message.reply_text(f"Contract owner: {owner}")
        else:
            await update.message.reply_text("Contract does not have an 'owner' function")
    except Exception as e:
        logger.error(f"Error checking owner: {str(e)}")
        await update.message.reply_text(f"Error checking owner: {str(e)}")

async def check_constant(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    constant_functions = [
        'MAX_EXTRA_REWARDS', 'MINIMUM_RECOVER_DURATION', 'allowExtraRewards',
        'durationInBlock', 'extraRewardsLength', 'newRewardRatio', 'rewardToken', 'stakingToken'
    ]
    
    for func_name in constant_functions:
        try:
            result = getattr(staking_contract.functions, func_name)().call()
            await update.message.reply_text(f"{func_name}(): {result}")
            return
        except Exception as e:
            logger.error(f"Error calling {func_name}: {str(e)}")
    
    await update.message.reply_text("Unable to call any constant functions")

async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        events = [event['name'] for event in STAKING_ABI if event['type'] == 'event']
        if events:
            message = "Available events in the staking contract:\n" + "\n".join(events)
        else:
            message = "No events found in the contract ABI."
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error listing events: {str(e)}")
        await update.message.reply_text(f"Error listing events: {str(e)}")

async def get_contract_bytecode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        bytecode = w3.eth.get_code(STAKING_CONTRACT_ADDRESS)
        if bytecode == '0x':
            await update.message.reply_text("No bytecode found at the specified address.")
        else:
            await update.message.reply_text(f"Bytecode found. Length: {len(bytecode)} bytes")
    except Exception as e:
        await update.message.reply_text(f"Error getting contract bytecode: {str(e)}")

async def query_past_events(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Try to get the latest 10 blocks
        latest_block = w3.eth.get_block('latest')['number']
        
        event_filter = staking_contract.events.Staked.create_filter(fromBlock=np.from_dlpack)
        events = event_filter.get_all_entries()
        
        if events:
            message = f"Found {len(events)} Staked events in the last 10 blocks."
        else:
            message = "No Staked events found in the last 10 blocks."
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error querying past events: {str(e)}")
        await update.message.reply_text(f"Error querying past events: {str(e)}")

async def check_specific_constant(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        result = staking_contract.functions.MAX_EXTRA_REWARDS().call()
        await update.message.reply_text(f"MAX_EXTRA_REWARDS: {result}")
    except Exception as e:
        logger.error(f"Error calling MAX_EXTRA_REWARDS: {str(e)}")
        await update.message.reply_text(f"Error calling MAX_EXTRA_REWARDS: {str(e)}")

async def check_web3_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        provider = w3.provider
        is_connected = w3.is_connected()
        chain_id = w3.eth.chain_id
        gas_price = w3.eth.gas_price
        
        message = f"Web3 Provider: {type(provider)}\n"
        message += f"Connected: {is_connected}\n"
        message += f"Chain ID: {chain_id}\n"
        message += f"Current Gas Price: {gas_price} Wei"
        
        await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Error checking Web3 details: {str(e)}")
        await update.message.reply_text(f"Error checking Web3 details: {str(e)}")

async def check_contract_functions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    functions_to_check = ['MAX_EXTRA_REWARDS', 'MINIMUM_RECOVER_DURATION', 'allowExtraRewards', 'totalSupply', 'rewardRate']
    
    message = "Contract function check results:\n"
    for func_name in functions_to_check:
        try:
            result = getattr(staking_contract.functions, func_name)().call()
            message += f"{func_name}: {result}\n"
        except ContractLogicError as e:
            message += f"{func_name}: Contract logic error - {str(e)}\n"
        except Exception as e:
            message += f"{func_name}: Error - {str(e)}\n"
    
    await update.message.reply_text(message)

# Add these new functions

async def check_contract_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        code = w3.eth.get_code(STAKING_CONTRACT_ADDRESS)
        if code == '0x':
            await update.message.reply_text(f"No contract found at address {STAKING_CONTRACT_ADDRESS}")
        else:
            await update.message.reply_text(f"Contract found at address {STAKING_CONTRACT_ADDRESS}")
    except Exception as e:
        await update.message.reply_text(f"Error checking contract address: {str(e)}")

async def check_abi(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        abi_functions = [f['name'] for f in STAKING_ABI if f['type'] == 'function']
        await update.message.reply_text(f"ABI contains these functions: {', '.join(abi_functions)}")
    except Exception as e:
        await update.message.reply_text(f"Error checking ABI: {str(e)}")

async def check_simple_view(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Try to call 'totalSupply' which is in the ABI
        result = staking_contract.functions.totalSupply().call()
        await update.message.reply_text(f"Total Supply: {Web3.from_wei(result, 'ether')} tokens")
    except Exception as e:
        await update.message.reply_text(f"Error calling totalSupply: {str(e)}")

async def check_paused(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if 'paused' in [func['name'] for func in STAKING_ABI if func['type'] == 'function']:
            paused = staking_contract.functions.paused().call()
            await update.message.reply_text(f"Contract paused: {paused}")
        else:
            await update.message.reply_text("Contract does not have a 'paused' function")
    except Exception as e:
        await update.message.reply_text(f"Error checking paused status: {str(e)}")

async def check_bytecode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        bytecode = w3.eth.get_code(STAKING_CONTRACT_ADDRESS)
        if bytecode == '0x':
            logger.warning(f"No bytecode found at address {STAKING_CONTRACT_ADDRESS}")
            await update.message.reply_text("No bytecode found at the specified address.")
        else:
            logger.info(f"Bytecode found at {STAKING_CONTRACT_ADDRESS}. Length: {len(bytecode)} bytes")
            await update.message.reply_text(f"Bytecode found. Length: {len(bytecode)} bytes")
    except Exception as e:
        logger.error(f"Error getting contract bytecode: {str(e)}")
        await update.message.reply_text(f"Error getting contract bytecode: {str(e)}")

async def check_contract_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        balance = w3.eth.get_balance(STAKING_CONTRACT_ADDRESS)
        balance_eth = Web3.from_wei(balance, 'ether')
        await update.message.reply_text(f"Contract balance: {balance_eth} ETH")
    except Exception as e:
        logger.error(f"Error checking contract balance: {str(e)}")
        await update.message.reply_text(f"Error checking contract balance: {str(e)}")

async def check_contract_functions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    functions_to_check = ['MAX_EXTRA_REWARDS', 'MINIMUM_RECOVER_DURATION', 'allowExtraRewards', 'totalSupply', 'rewardRate', 'owner', 'paused']
    
    message = "Contract function check results:\n"
    for func_name in functions_to_check:
        try:
            result = getattr(staking_contract.functions, func_name)().call()
            message += f"{func_name}: {result}\n"
        except ContractLogicError as e:
            message += f"{func_name}: Contract logic error - {str(e)}\n"
        except Exception as e:
            message += f"{func_name}: Error - {str(e)}\n"
    
    await update.message.reply_text(message)

async def check_implementation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        implementation = staking_contract.functions.implementation().call()
        await update.message.reply_text(f"Implementation address: {implementation}")
    except Exception as e:
        await update.message.reply_text(f"Error checking implementation: {str(e)}")

async def print_abi_functions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        functions = [f['name'] for f in STAKING_ABI if f['type'] == 'function']
        message = "Functions in ABI:\n" + "\n".join(functions)
        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(f"Error printing ABI functions: {str(e)}")

async def check_proxy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # This is a common storage slot for the implementation address in proxy contracts
        implementation_slot = '0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc'
        implementation_address = w3.eth.get_storage_at(STAKING_CONTRACT_ADDRESS, implementation_slot)
        implementation_address = '0x' + implementation_address.hex()[-40:]
        await update.message.reply_text(f"Possible implementation address: {implementation_address}")
    except Exception as e:
        await update.message.reply_text(f"Error checking proxy: {str(e)}")

async def fetch_autopool_data(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        autopool_address = '0x0A2b94F6871c1D7A32Fe58E1ab5e6deA2f114E56'
        
        # ABI for the totalSupply function
        abi = [{"inputs":[],"name":"totalSupply","outputs":[{"internalType":"uint256","name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]
        
        contract = w3.eth.contract(address=autopool_address, abi=abi)
        total_supply = contract.functions.totalSupply().call()
        
        # Convert wei to ether
        total_supply_eth = w3.from_wei(total_supply, 'ether')
        
        message = f"Autopool Total Supply: {total_supply_eth:.2f} tokens"
        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(f"Error fetching autopool data: {str(e)}")

async def fetch_top_depositors(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pool_address = "0x0A2b94F6871c1D7A32Fe58E1ab5e6deA2f114E56"
    url = f"https://api.tokemak.xyz/v1/pools/{pool_address}/depositors"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    depositors = data.get('depositors', [])
                    
                    if not depositors:
                        await update.message.reply_text("No depositor data available.")
                        return

                    # Sort depositors by balance in descending order
                    sorted_depositors = sorted(depositors, key=lambda x: x['balance'], reverse=True)
                    
                    # Get top 10 depositors
                    top_10 = sorted_depositors[:10]
                    
                    message = "Top 10 Depositors:\n\n"
                    for i, depositor in enumerate(top_10, 1):
                        address = depositor['address']
                        balance = depositor['balance']
                        message += f"{i}. Address: {address[:6]}...{address[-4:]}\n   Balance: {balance:.4f} ETH\n\n"
                    
                    await update.message.reply_text(message)
                else:
                    await update.message.reply_text(f"Error fetching data: HTTP {response.status}")
    except aiohttp.ClientConnectorError:
        await update.message.reply_text("Unable to connect to the Tokemak API. The service might be temporarily unavailable.")
    except asyncio.TimeoutError:
        await update.message.reply_text("The request to the Tokemak API timed out. Please try again later.")
    except Exception as e:
        logger.error(f"Error in fetch_top_depositors: {str(e)}")
        await update.message.reply_text("An unexpected error occurred while fetching top depositors. Please try again later.")

async def fetch_contract_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        contract_address = "0x0A2b94F6871c1D7A32Fe58E1ab5e6deA2f114E56"
        url = f"https://api.etherscan.io/api?module=contract&action=getabi&address={contract_address}&apikey={ETHERSCAN_API_KEY}"
        response = requests.get(url)
        response.raise_for_status()
        
        data = response.json()
        
        if data['status'] == '1':
            message = "Contract Information:\n\n"
            message += f"Contract Address: {contract_address}\n"
            message += "Contract is verified on Etherscan\n"
        else:
            message = f"Unable to fetch contract information: {data['message']}"
        
        await update.message.reply_text(message)
    except requests.RequestException as e:
        await update.message.reply_text(f"Error fetching data from Etherscan API: {str(e)}")
    except Exception as e:
        await update.message.reply_text(f"Error processing API data: {str(e)}")

async def fetch_contract_balance(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        contract_address = "0x0A2b94F6871c1D7A32Fe58E1ab5e6deA2f114E56"
        url = f"https://api.etherscan.io/api?module=account&action=balance&address={contract_address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
        response = requests.get(url)
        response.raise_for_status()
        
        data = response.json()
        
        if data['status'] == '1':
            balance_wei = int(data['result'])
            balance_eth = balance_wei / 1e18  # Convert wei to ETH
            message = f"Contract Balance: {balance_eth:.4f} ETH"
        else:
            message = f"Unable to fetch contract balance: {data['message']}"
        
        await update.message.reply_text(message)
    except requests.RequestException as e:
        await update.message.reply_text(f"Error fetching data from Etherscan API: {str(e)}")
    except Exception as e:
        await update.message.reply_text(f"Error processing API data: {str(e)}")

async def tokemak_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Tokemak Autopilot\n\n"
        "Tokemak Autopilot is a system of smart contracts for automated liquidity management. "
        "The core contracts are open-source and available on GitHub.\n\n"
        "Key features:\n"
        "- Automated liquidity deployment\n"
        "- ERC4626 compliant vaults\n"
        "- Extensive testing including fuzz tests\n\n"
        "For more information, visit: https://github.com/Tokemak/v2-core-pub"
    )
    await update.message.reply_text(message)

async def tokemak_tests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Running Tokemak Autopilot Tests\n\n"
        "Basic unit tests, integration tests, and Foundry-based fuzz tests can be run with:\n"
        "`forge test`\n\n"
        "To run ERC4626 prop fuzz tests against the Autopool:\n"
        "`forge test --match-path test/fuzz/vault/Autopool.t.sol --fuzz-runs 10000`\n\n"
        "For more details, visit: https://github.com/Tokemak/v2-core-pub#running-tests"
    )
    await update.message.reply_text(message)

async def tokemak_deployment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Tokemak Autopilot Deployment\n\n"
        "Deployment commands for different networks:\n\n"
        "Mainnet:\n"
        "`forge script script/01_SystemDeploy.s.sol --rpc-url mainnet --sender $V2DEPLOY2`\n\n"
        "Base:\n"
        "`forge script script/01_SystemDeploy.s.sol --rpc-url mainnet --sender $V2DEPLOY2 --account v2-base-guarded`\n\n"
        "Sepolia:\n"
        "`forge script script/sepolia/01_InitToke.s.sol --rpc-url sepolia --sender $SENDER_SEPOLIA --account v2-sepolia`\n\n"
        "For more details, visit: https://github.com/Tokemak/v2-core-pub#deployment"
    )
    await update.message.reply_text(message)

async def autopilot_contracts(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Tokemak Autopilot Main Contracts:\n\n"
        "1. LMPVault: The main vault contract for liquidity management\n"
        "2. DestinationVault: Represents a specific liquidity destination\n"
        "3. LMPVaultRouter: Handles routing of funds between vaults\n"
        "4. LMPVaultFactory: Factory contract for creating new LMP Vaults\n"
        "5. DestinationVaultFactory: Factory for creating new Destination Vaults\n"
        "6. MainRewarder: Handles reward distribution for staking\n"
        "7. AsyncSwapper: Manages asynchronous token swaps\n\n"
        "These contracts work together to manage liquidity and automate rebalancing in the Tokemak ecosystem."
    )
    await update.message.reply_text(message)

async def autopilot_key_functions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Key Functions of Tokemak Autopilot:\n\n"
        "1. deposit(): Allows users to deposit assets into the LMP Vault\n"
        "2. withdraw(): Enables users to withdraw their assets from the vault\n"
        "3. rebalance(): Triggers the rebalancing process to optimize liquidity allocation\n"
        "4. addDestination(): Adds a new destination for liquidity deployment\n"
        "5. removeDestination(): Removes a destination from the available options\n"
        "6. setDestinationAllocation(): Updates the allocation for a specific destination\n"
        "7. claimRewards(): Allows users to claim their earned rewards\n\n"
        "These functions form the core of the Autopilot's functionality, enabling automated liquidity management."
    )
    await update.message.reply_text(message)

async def autopilot_rebalancing(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Tokemak Autopilot Rebalancing Process:\n\n"
        "1. Analysis: The system analyzes current market conditions and liquidity needs\n"
        "2. Calculation: Optimal liquidity distribution is calculated based on predefined strategies\n"
        "3. Execution: The rebalance() function is called, which:\n"
        "   a. Withdraws liquidity from underperforming or overallocated destinations\n"
        "   b. Swaps tokens as needed using the AsyncSwapper\n"
        "   c. Deploys liquidity to new or underallocated destinations\n"
        "4. Verification: The system checks that the new allocation matches the calculated optimal distribution\n"
        "5. Reward Update: Reward rates are adjusted based on the new allocation\n\n"
        "This process ensures that liquidity is continuously optimized for maximum efficiency and returns."
    )
    await update.message.reply_text(message)

async def v2_rebalance_dashboard_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "Tokemak v2 Rebalance Dashboard\n\n"
        "This dashboard visualizes rebalancing data for Tokemak's v2 system. "
        "It includes charts and data analysis for autopools and their performance.\n\n"
        "Key features:\n"
        "- Autopool top-level charts\n"
        "- Jupyter notebook for balETH dashboard MVP\n"
        "- Python scripts for data processing and visualization\n\n"
        "The dashboard helps in monitoring and analyzing the performance of Tokemak's automated rebalancing system.\n\n"
        "For more information, visit: https://github.com/Tokemak/v2-rebalance-dashboard"
    )
    await update.message.reply_text(message)

async def v2_dashboard_structure(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = (
        "v2 Rebalance Dashboard Project Structure\n\n"
        "- autopool_top_level_charts.py: Script for generating top-level charts for autopools\n"
        "- balETH dashboard MVP.ipynb: Jupyter notebook with the MVP for balETH dashboard\n"
        "- destination_df.csv: CSV file containing destination data\n"
        "- v2_rebalance_dashboard/: Directory containing main dashboard code\n"
        "- tests/: Directory for test files\n"
        "- mainnet_launch/: Directory related to mainnet launch\n\n"
        "Key files:\n"
        "- pyproject.toml: Project configuration and dependencies\n"
        "- README.md: Project documentation\n"
        "- .env_example: Example environment variable file\n\n"
        "For more details, explore the repository: https://github.com/Tokemak/v2-rebalance-dashboard"
    )
    await update.message.reply_text(message)

# Assuming you have a minimal ERC20 ABI defined
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function"
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function"
    }
]

async def get_balance(address):
    url = f"https://api.etherscan.io/api?module=account&action=balance&address={address}&tag=latest&apikey={ETHERSCAN_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            if data['status'] == '1':
                return Decimal(Web3.from_wei(int(data['result']), 'ether'))
            else:
                print(f"Error getting balance for {address}: {data['message']}")
                return Decimal(0)

async def get_token_balance(token_address, wallet_address):
    token_contract = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
    balance = token_contract.functions.balanceOf(wallet_address).call()
    decimals = token_contract.functions.decimals().call()
    return Decimal(balance) / Decimal(10 ** decimals)

async def get_pool_info(pool_address):
    contract = w3.eth.contract(address=Web3.to_checksum_address(pool_address), abi=ABI)
    try:
        total_assets = Decimal(Web3.from_wei(contract.functions.totalAssets().call(), 'ether'))
        
        destinations = contract.functions.getDestinations().call()
        destination_info = {}
        total_deployed = Decimal(0)
        
        for dest in destinations:
            try:
                dest_contract = w3.eth.contract(address=Web3.to_checksum_address(dest), abi=ERC20_ABI)
                token_name = dest_contract.functions.name().call()
                
                balance = await get_token_balance(dest, pool_address)
                total_deployed += balance
                
                destination_info[dest] = {
                    'name': token_name,
                    'balance': balance
                }
                print(f"Destination {token_name}: balance = {balance}")
            except Exception as e:
                print(f"Error processing destination {dest}: {str(e)}")
                destination_info[dest] = {
                    'name': f"Unknown ({dest[:6]}...{dest[-4:]})",
                    'balance': Decimal(0)
                }
        
        print(f"Total assets: {total_assets}, Total deployed: {total_deployed}")
        
        # Calculate percentages
        for dest in destination_info:
            percentage = (destination_info[dest]['balance'] / total_assets * 100) if total_assets > 0 else 0
            destination_info[dest]['percentage'] = percentage
            print(f"Destination {destination_info[dest]['name']}: percentage = {percentage}%")
        
        eth_price = await get_eth_price()
        tvl = total_assets * Decimal(eth_price)
        
        return total_assets, tvl, destination_info, eth_price
    except Exception as e:
        print(f"Error in get_pool_info for {pool_address}: {str(e)}")
        return None

async def get_eth_price():
    url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            return Decimal(str(data['ethereum']['usd']))

async def get_defi_llama_data():
    url = 'https://yields.llama.fi/pools'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status == 200:
                data = await response.json()
                pools = [p for p in data['data'] if p['pool'] in pool_ids]
                logger.info(f"Tokemak pools found in DeFi Llama: {[pool_ids[p['pool']] for p in pools]}")
                return pools
    logger.warning("Failed to fetch Tokemak pools from DeFi Llama")
    return []

async def get_defi_llama_apy(pool_name, tokemak_pools):
    logger.info(f"Searching for {pool_name} in DeFi Llama data")
    for pool in tokemak_pools:
        if pool_ids[pool['pool']] == pool_name:
            apy = pool.get('apy', 0)
            tvl = pool.get('tvlUsd', 0)
            logger.info(f"Found data for {pool_name}: APY={apy}, TVL=${tvl}")
            return apy, tvl
    logger.warning(f"No data found for {pool_name} in DeFi Llama")
    return None, None

async def get_pool_metrics(pool_address, pool_name):
    pool_info = await get_pool_info(pool_address)
    if pool_info is None:
        return None, f"Failed to get info for {pool_name} pool"

    total_assets, tvl, destination_info, eth_price = pool_info
    
    tokemak_pools = await get_defi_llama_data()
    apy, tvl = await get_defi_llama_apy(pool_name, tokemak_pools)
    
    # Filter out zero-value assets
    destination_info = {k: v for k, v in destination_info.items() if v['balance'] > 0}
    
    fig, (ax_text, ax_pie, ax_legend) = plt.subplots(3, 1, figsize=(10, 10), facecolor='black', 
                                                     gridspec_kw={'height_ratios': [1, 3, 1.2]})
    fig.suptitle(f"\n\n{pool_name} Pool Overview", color='white', fontsize=24, y=0.98, fontweight='bold')
    
    # Text information
    text = f"Total Assets: {total_assets:.2f} ETH\n"
    if apy is not None:
        text += f"APY: {apy:.2f}%"
    if tvl is not None:
        text += f" | TVL: ${tvl:,.2f}"
    text += f"\nETH Price: ${eth_price:,.2f}"
    
    ax_text.text(0.5, 0.5, text, color='white', fontsize=14, 
                 verticalalignment='center', horizontalalignment='center', 
                 transform=ax_text.transAxes)
    ax_text.axis('off')
    
    # Pie chart
    sizes = [info['percentage'] for info in destination_info.values()]
    labels = [info['name'].replace('Tokemak-Wrapped Ether-', '').replace('Tokemak-', '') for info in destination_info.values()]
    
    # Define colors for the pie chart
    colors = ['#B5FF00', '#00B5FF', '#BF5AF2', '#FF9500', '#FF2D55']
    
    wedges, texts = ax_pie.pie(sizes, labels=labels, colors=colors, 
                               startangle=90, labeldistance=1.05)
    ax_pie.set_title("Destination Distribution", color='white', fontsize=16)
    
    # Remove labels from the pie chart to avoid overlapping
    for text in texts:
        text.set_visible(False)
    
    # Create a legend with percentages and balances
    legend_labels = [f"{label} ({info['percentage']:.1f}%, {info['balance']:.2f} ETH)" 
                     for label, info in zip(labels, destination_info.values())]
    
    # Use ax_legend for the legend
    ax_legend.axis('off')
    ax_legend.legend(wedges, legend_labels, title="Destinations", 
                     loc="center", fontsize=10, title_fontsize=12)
    
    plt.tight_layout()
    fig.subplots_adjust(top=0.9, bottom=0.05, hspace=0.05)
    
    # Add colored line at the top
    fig.add_artist(plt.Line2D([0, 1], [0.955, 0.955], color='#B5FF00', linewidth=2, transform=fig.transFigure))
    
    buf = io.BytesIO()
    plt.savefig(buf, format='png', facecolor='black', edgecolor='none', bbox_inches='tight', dpi=300)
    buf.seek(0)
    plt.close(fig)
    
    return buf, None

async def autoETH(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        image, error_message = await get_pool_metrics(POOLS['autoETH'], 'autoETH')
        if image:
            await update.message.reply_photo(image)
        else:
            await update.message.reply_text(error_message)
    except Exception as e:
        logger.error(f"Error in autoETH: {str(e)}")
        await update.message.reply_text(f"Error fetching autoETH metrics: {str(e)}")

async def autoLRT(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        image, error_message = await get_pool_metrics(POOLS['autoLRT'], 'autoLRT')
        if image:
            await update.message.reply_photo(image)
        else:
            await update.message.reply_text(error_message)
    except Exception as e:
        logger.error(f"Error in autoLRT: {str(e)}")
        await update.message.reply_text(f"Error fetching autoLRT metrics: {str(e)}")

async def balETH(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        image, error_message = await get_pool_metrics(POOLS['balETH'], 'balETH')
        if image:
            await update.message.reply_photo(image)
        else:
            await update.message.reply_text(error_message)
    except Exception as e:
        logger.error(f"Error in balETH: {str(e)}")
        await update.message.reply_text(f"Error fetching balETH metrics: {str(e)}")

async def tokemak_tvl(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # API endpoint to get protocol data
        url = 'https://api.llama.fi/protocol/tokemak'

        # Make the request to the DeFi Llama API to get the protocol data
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            
            # Extract the current overall TVL
            overall_tvl = data['currentChainTvls'].get('Ethereum', 0)
            
            # Extract the historical TVL data
            historical_tvl = data.get('chainTvls', {}).get('Ethereum', {}).get('tvl', [])
            
            # Filter TVL data for the last month
            one_month_ago = datetime.now() - timedelta(days=30)
            filtered_tvl = [
                (datetime.fromtimestamp(item['date']), item['totalLiquidityUSD'])
                for item in historical_tvl if datetime.fromtimestamp(item['date']) >= one_month_ago
            ]
            
            # Separate the dates and TVLs for plotting
            dates, tvls = zip(*filtered_tvl)
            
            # Create the plot
            fig, ax = plt.subplots(figsize=(10, 6), facecolor='black')
            ax.set_facecolor('black')
            
            ax.plot(dates, tvls, color='#B5FF00', linewidth=2)
            
            plt.title('Tokemak TVL Over the Last Month', color='white', fontsize=16)
            plt.xlabel('Date', color='white', fontsize=12)
            plt.ylabel('TVL (USD)', color='white', fontsize=12)
            
            plt.tick_params(axis='x', colors='white')
            plt.tick_params(axis='y', colors='white')
            
            for spine in ax.spines.values():
                spine.set_color('white')
            
            plt.grid(color='gray', linestyle='--', alpha=0.3)
            
            # Format y-axis labels to show in billions
            ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1e9:.1f}B'))
            
            # Rotate and align the tick labels so they look better
            plt.gcf().autofmt_xdate()
            
            # Save the plot to a buffer
            buf = io.BytesIO()
            plt.savefig(buf, format='png', facecolor='black', edgecolor='none', bbox_inches='tight')
            buf.seek(0)
            
            # Send the image
            await update.message.reply_photo(buf, caption=f"Tokemak Total TVL: ${overall_tvl:,.2f}")
            
            # Close the plot to free up memory
            plt.close(fig)

        else:
            await update.message.reply_text(f"Error fetching data: {response.status_code}")
    except Exception as e:
        logger.error(f"Error in tokemak_tvl: {str(e)}")
        await update.message.reply_text(f"Error fetching Tokemak TVL: {str(e)}")

async def pool_summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        total_assets = {}
        for pool_name, address in POOLS.items():
            pool_info = await get_pool_info(address)
            if pool_info:
                total_assets[pool_name], _, _, _ = pool_info

        fig, ax = plt.subplots(figsize=(10, 6), facecolor='black')
        ax.set_facecolor('black')

        pools = list(total_assets.keys())
        values = list(total_assets.values())

        # Define base colors for each bar
        base_colors = {'autoETH': '#B5FF00', 'autoLRT': '#00B5FF', 'balETH': '#BF5AF2'}

        # Create gradients
        for i, (pool, value) in enumerate(zip(pools, values)):
            base_color = base_colors[pool]
            r, g, b = [int(base_color[j:j+2], 16)/255 for j in (1, 3, 5)]
            gradient = LinearSegmentedColormap.from_list("", [(r, g, b, 1), (r/4, g/4, b/4, 1)])
            ax.bar(i, value, color=gradient(np.linspace(0, 1, 256)))

        plt.title('Total Assets Distribution Across Pools', color='white', fontsize=16)
        plt.xlabel('Pools', color='white', fontsize=12)
        plt.ylabel('Total Assets (ETH)', color='white', fontsize=12)
        plt.xticks(range(len(pools)), pools, color='white')
        plt.tick_params(axis='y', colors='white')

        for spine in ax.spines.values():
            spine.set_color('white')

        # Add value labels on top of each bar
        for i, v in enumerate(values):
            ax.text(i, v, f'{v:.2f}', ha='center', va='bottom', color='white')

        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', facecolor='black', edgecolor='none')
        buf.seek(0)
        plt.close(fig)

        # Send the chart
        await update.message.reply_photo(buf, caption="Total Assets Distribution Across Pools")

    except Exception as e:
        logger.error(f"Error in pool_summary: {str(e)}")
        await update.message.reply_text(f"Error fetching pool summary: {str(e)}")

GITBOOK_URL = "https://docs.tokemak.xyz/"
MAX_MESSAGE_LENGTH = 4096

# Add this global variable to store the GitBook content
def load_gitbook_content(autopool_info):
    global gitbook_content
    gitbook_path = r'C:\Users\ROBERT\Desktop\TOKENBBOT\app\Restructured_Tokemak_Gitbook.json'
    print(f"Attempting to load GitBook content from: {gitbook_path}")
    if os.path.exists(gitbook_path):
        with open(gitbook_path, 'r', encoding='utf-8') as file:
            gitbook_data = json.load(file)
            print(f"Loaded JSON data. Type: {type(gitbook_data)}")
            print(f"Keys in gitbook_data: {list(gitbook_data.keys())}")
            
            # Extract content from the nested structure
            content_list = []
            for section, content in gitbook_data.items():
                if isinstance(content, dict):
                    for subsection, text in content.items():
                        if isinstance(text, str):
                            content_list.append(f"{section} - {subsection}:\n{text}")
                elif isinstance(content, str):
                    content_list.append(f"{section}:\n{content}")
            
            gitbook_content = '\n\n'.join(content_list)
            
            # Add AUTOPOOL_INFO to gitbook_content
            gitbook_content += "\n\n" + autopool_info
            
            print(f"Combined content length: {len(gitbook_content)} characters")
            if gitbook_content:
                print(f"Sample of content: {gitbook_content[:200]}...")  # Print first 200 characters
            else:
                print("Warning: gitbook_content is empty after processing")
    else:
        print(f"GitBook content file not found at {gitbook_path}")
        gitbook_content = ""
    
    if not gitbook_content:
        print("Warning: gitbook_content is empty after loading")
    else:
        print("GitBook content loaded successfully")

async def scrape_gitbook(urls):
    global gitbook_content
    gitbook_content = ""
    
    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        content = await response.text()
                        soup = BeautifulSoup(content, 'html.parser')
                        
                        # Find the main content
                        main_content = soup.find('div', {'class': 'markdown-body'})
                        if main_content:
                            # Extract the title
                            title = soup.find('h1')
                            title_text = title.text if title else "Untitled"
                            
                            # Add the title and content to gitbook_content
                            gitbook_content += f"\n\n{title_text}:\n{main_content.get_text()}"
                        else:
                            logger.warning(f"No main content found for {url}")
                    else:
                        logger.warning(f"Failed to fetch {url}: HTTP {response.status}")
            except Exception as e:
                logger.error(f"Error scraping {url}: {str(e)}")
    
    logger.info(f"Scraped content from {len(urls)} pages")
    return gitbook_content

# List of URLs to scrape
urls_to_scrape = [
    "https://docs.tokemak.xyz//",
    "https://docs.tokemak.xyz//autopilot/a-new-way-to-provide-liquidity",
    "https://docs.tokemak.xyz//autopilot/protocol-mechanics",
    "https://docs.tokemak.xyz//autopilot/protocol-mechanics/components-and-logic",
    "https://docs.tokemak.xyz//autopilot/protocol-mechanics/asset-flow-example",
    "https://docs.tokemak.xyz//autopilot/autopools-and-lats",
    "https://docs.tokemak.xyz//autopilot/custom-autopools",
    "https://docs.tokemak.xyz//autopilot/glossary",
    "https://docs.tokemak.xyz//using-the-app/app-guide",
    "https://docs.tokemak.xyz//using-the-app/app-guide/autopools",
    "https://docs.tokemak.xyz//using-the-app/app-guide/autopools/deposit-and-withdraw",
    "https://docs.tokemak.xyz//using-the-app/app-guide/autopools/stake-and-unstake",
    "https://docs.tokemak.xyz//using-the-app/app-guide/autopools/claim-incentives",
    "https://docs.tokemak.xyz//using-the-app/app-guide/autopools/view-positions",
    "https://docs.tokemak.xyz//using-the-app/app-guide/locked-toke",
    "https://docs.tokemak.xyz//using-the-app/app-guide/locked-toke/lock-and-earn",
    "https://docs.tokemak.xyz//using-the-app/app-guide/locked-toke/claim-rewards",
    "https://docs.tokemak.xyz//using-the-app/app-guide/locked-toke/view-positions",
    "https://docs.tokemak.xyz//using-the-app/app-guide/toke-eth-lp",
    "https://docs.tokemak.xyz//using-the-app/troubleshooting",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-system-high-level-overview",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems/autopilot-contract-security",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems/stats",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems/autopilot-strategy",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems/pricing",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems/swap-router",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems/curve-resolver",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems/message-proxy",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems/acctoke",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems/autopilot-router",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems/liquidation",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems/destination-vaults",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-and-systems/autopools",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/autopool-eth-contracts-overview/autopilot-contracts-glossary",
    "https://docs.tokemak.xyz//developer-docs/contracts-overview/contract-addresses",
    "https://docs.tokemak.xyz//developer-docs/security-and-audits",
    "https://docs.tokemak.xyz//developer-docs/security-and-audits/hexens-autopilot-follow-up-updates-audit-july-2024",
    "https://docs.tokemak.xyz//developer-docs/security-and-audits/hexens-tokemak-autopilot-may-2024",
    "https://docs.tokemak.xyz//developer-docs/security-and-audits/certora-lmpstrategy-security-assessment-and-formal-verification-report-jan-march-2024",
    "https://docs.tokemak.xyz//developer-docs/security-and-audits/hats.finance-crowd-competition-smart-contract-audit-february-march-2024",
    "https://docs.tokemak.xyz//developer-docs/security-and-audits/halborn-autopilot-autopools-contracts-preliminary-smart-contract-audit-sept-2023",
    "https://docs.tokemak.xyz//developer-docs/security-and-audits/halborn-autopilot-pricing-contracts-formal-verification-report-sept-2023",
    "https://docs.tokemak.xyz//developer-docs/security-and-audits/sherlock-autopilot-contracts-crowd-competition-sept-2023",
    "https://docs.tokemak.xyz//developer-docs/security-and-audits/halborn-acctoke-contract-nov-2022",
    "https://docs.tokemak.xyz//additional-links/community-resources",
    "https://www.gitbook.com/?utm_source=content&utm_medium=trademark&utm_campaign=2A6wmAnkpzrcydAUxLkR",
    "https://docs.tokemak.xyz//~gitbook/pdf?page=vFwHTgRpmvU3WaMZfpSu&only=yes",
    "https://docs.tokemak.xyz//autopilot/a-new-way-to-provide-liquidity"
]

# In your main function or wherever you initialize your bot:
async def initialize_content():
    global gitbook_content
    gitbook_content = await scrape_gitbook(urls_to_scrape)

# Make sure to call this function before starting your bot
# For example, in your main() function:
async def main():
    await initialize_content()
    # ... rest of your main function

async def gitbook_index(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        index = await scrape_gitbook(GITBOOK_URL)
        
        # Filter out categories with no items
        categories = [cat for cat, items in index.items() if items]
        
        keyboard = [
            [InlineKeyboardButton(category, callback_data=f"category_{i}")]
            for i, category in enumerate(categories)
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text("Please select a main section:", reply_markup=reply_markup)
        
        context.user_data['gitbook_index'] = index
        context.user_data['gitbook_categories'] = categories

    except Exception as e:
        logger.error(f"Error in gitbook_index: {str(e)}")
        await update.message.reply_text("An error occurred while fetching the GitBook index. Please try again later.")

# Add this new function to handle user questions
import openai

# Load environment variables from .env.txt file
dotenv_path = r'C:\Users\ROBERT\Desktop\TOKENBBOT\.env.txt'
load_dotenv(dotenv_path)

# Get the API key from environment variables
openai.api_key = os.getenv('OPENAI_API_KEY')

OPENAI_ENABLED = True  # Set this to True when the API is working again

async def answer_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global gitbook_content
    
    if not OPENAI_ENABLED:
        await update.message.reply_text(
            "Oh, the AI is taking a nap. Maybe try asking your toaster for advice? Or just wait a bit."
        )
        return

    if not gitbook_content:
        await update.message.reply_text("Oops! Looks like my brain is on vacation. Try again later.")
        return

    question = ' '.join(context.args)
    if not question:
        await update.message.reply_text("You forgot to ask a question. Or did you just want to hear me talk?")
        return

    if "address" in question.lower() and "autopool" in question.lower():
        await update.message.reply_text(f"Looking for Autopool addresses? Here you go:\n\n{AUTOPOOL_INFO}")
        return

    prompt = f"""Based on the following information about Tokemak, please answer the question: '{question}'
    If the question is about Autopool addresses, make sure to include the specific contract addresses in your answer.
    Respond as a college professor conducting a one-on-one session with a student.
    Use clear, precise language and provide detailed explanations to ensure understanding.
    Your explanation should be insightful and educational, while still conveying accurate information about Tokemak and blockchain.
    Begin with a brief overview of the topic.
    Limit your response to two or three concise, informative paragraphs.
    
    Information: {AUTOPOOL_INFO}

    Additional Information: {gitbook_content[:3500]}"""

    try:
        client = openai.OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a college professor conducting a one-on-one session with a student. Use clear, precise language and provide detailed explanations to ensure understanding. Your responses should be insightful and educational, yet accurately convey information. Always begin with a brief overview of the topic. Limit your responses to two or three concise, informative paragraphs."},
                {"role": "user", "content": prompt}
            ]
        )
        answer = response.choices[0].message.content.strip()
        
        # Split the answer into paragraphs
        paragraphs = answer.split('\n\n')
        
        # Limit to 2-3 paragraphs
        if len(paragraphs) > 3:
            answer = '\n\n'.join(paragraphs[:3])
        
        await update.message.reply_text(answer)
    except openai.RateLimitError as e:
        logger.error(f"OpenAI API rate limit exceeded: {str(e)}")
        await update.message.reply_text("Looks like the AI is too popular right now. Try again later, if you dare.")
    except openai.APIError as e:
        logger.error(f"OpenAI API error: {str(e)}")
        await update.message.reply_text("Oops, something went wrong. Maybe the AI is having a bad day.")
    except Exception as e:
        logger.error(f"Error in OpenAI API call: {str(e)}")
        await update.message.reply_text("An unexpected error occurred. But hey, at least it's not boring!")

async def category_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    category_index = int(query.data.split('_')[1])
    categories = context.user_data.get('gitbook_categories', [])
    index = context.user_data.get('gitbook_index', {})

    if category_index < len(categories):
        category = categories[category_index]
        items = index.get(category, [])

        keyboard = [
            [InlineKeyboardButton(item['title'], callback_data=f"section_{category_index}_{i}")]
            for i, item in enumerate(items)
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(f"Sections in {category}:", reply_markup=reply_markup)
    else:
        await query.edit_message_text("Invalid category selection.")

async def section_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    _, category_index, section_index = query.data.split('_')
    category_index, section_index = int(category_index), int(section_index)

    categories = context.user_data.get('gitbook_categories', [])
    index = context.user_data.get('gitbook_index', {})

    if category_index < len(categories):
        category = categories[category_index]
        items = index.get(category, [])
        if section_index < len(items):
            section = items[section_index]
            await query.edit_message_text(f"Section: {section['title']}\nURL: {section['url']}")
        else:
            await query.edit_message_text("Invalid section selection.")
    else:
        await query.edit_message_text("Invalid category selection.")

async def check_ai_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if OPENAI_ENABLED:
        await update.message.reply_text("The AI answering feature is currently enabled.")
    else:
        await update.message.reply_text("The AI answering feature is currently disabled. Please try again later.")

# Add this near the top of your file, after the imports and before the main function
AUTOPOOL_INFO = """
Autopool Addresses:
autoETH: 0x0A2b94F6871c1D7A32Fe58E1ab5e6deA2f114E56
autoLRT: 0xe800e3760fc20aa98c5df6a9816147f190455af3
balETH: 0x6dC3ce9C57b20131347FDc9089D740DAf6eB34c5

These are the main contract addresses for Tokemak's Autopools. 
autoETH and autoLRT are Ethereum-based pools, while balETH is a Balancer pool.
"""

def main() -> None:
    print("Script started")
    try:
        print("Entering main function")
        load_gitbook_content(AUTOPOOL_INFO)  # Load GitBook content at the start
        print("Building application")
        application = Application.builder().token(TOKEN).build()

        print("Adding command handlers")
        # Add your command handlers here
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("check_contract_balance", check_contract_balance))
        application.add_handler(CommandHandler("check_contract_functions", check_contract_functions))
        application.add_handler(CommandHandler("check_implementation", check_implementation))
        application.add_handler(CommandHandler("print_abi_functions", print_abi_functions))
        application.add_handler(CommandHandler("check_proxy", check_proxy))
        application.add_handler(CommandHandler("fetch_autopool_data", fetch_autopool_data))
        application.add_handler(CommandHandler("fetch_top_depositors", fetch_top_depositors))
        application.add_handler(CommandHandler("fetch_contract_info", fetch_contract_info))
        application.add_handler(CommandHandler("fetch_contract_balance", fetch_contract_balance))
        application.add_handler(CommandHandler("tokemak_info", tokemak_info))
        application.add_handler(CommandHandler("tokemak_tests", tokemak_tests))
        application.add_handler(CommandHandler("tokemak_deployment", tokemak_deployment))
        application.add_handler(CommandHandler("autopilot_contracts", autopilot_contracts))
        application.add_handler(CommandHandler("autopilot_key_functions", autopilot_key_functions))
        application.add_handler(CommandHandler("autopilot_rebalancing", autopilot_rebalancing))
        application.add_handler(CommandHandler("v2_rebalance_dashboard_info", v2_rebalance_dashboard_info))
        application.add_handler(CommandHandler("v2_dashboard_structure", v2_dashboard_structure))
        application.add_handler(CommandHandler("autoETH", autoETH))
        application.add_handler(CommandHandler("autoLRT", autoLRT))
        application.add_handler(CommandHandler("balETH", balETH))
        application.add_handler(CommandHandler("tokemak_tvl", tokemak_tvl))
        application.add_handler(CommandHandler("pool_summary", pool_summary))
        application.add_handler(CommandHandler("gitbook_index", gitbook_index))
        application.add_handler(CommandHandler("ask", answer_question))
        application.add_handler(CallbackQueryHandler(category_callback, pattern=r'^category_'))
        application.add_handler(CallbackQueryHandler(section_callback, pattern=r'^section_'))
        application.add_handler(CommandHandler("ai_status", check_ai_status))

        print("Starting polling")
        application.run_polling()
        
    except Exception as e:
        print(f"Error in main function: {str(e)}")
        logger.error(f"Error in main function: {str(e)}")
        import traceback
        traceback.print_exc()  # This will print the full traceback

if __name__ == "__main__":
    print("Calling main function")
    main()
