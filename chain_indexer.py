"""
Direct Blockchain Indexing Core
Indexes DAOs using direct RPC connections and pattern matching
"""
import logging
import time
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta

import web3
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import BadFunctionCallOutput, ContractLogicError
import firebase_admin
from firebase_admin import firestore, credentials
import pandas as pd

from config import blockchain_config, firebase_config, dao_detection_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('arbiter_indexer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ChainIndexer:
    """Core blockchain indexer for DAO detection"""
    
    def __init__(self, chain_name: str = "ethereum"):
        """
        Initialize indexer for specific chain
        
        Args:
            chain_name: blockchain name (ethereum, polygon, arbitrum, optimism)
        """
        self.chain_name = chain_name
        self.rpc_url = self._get_rpc_url(chain_name)
        self.w3 = self._initialize_web3()
        self.db = self._initialize_firestore()
        self.dao_patterns = self._load_dao_patterns()
        
        # Statistics tracking
        self.stats = {
            "blocks_scanned": 0,
            "daos_detected": 0,
            "errors_encountered": 0,
            "last_block": 0
        }
        
        logger.info(f"ChainIndexer initialized for {chain_name} with RPC: {self.rpc_url[:50]}...")
    
    def _get_rpc_url(self, chain_name: str) -> str:
        """Get RPC URL for specific chain"""
        url_map = {
            "ethereum": blockchain_config.ETH_RPC_URL,
            "polygon": blockchain_config.POLYGON_RPC_URL,
            "solana": blockchain_config.SOLANA_RPC_URL
        }
        
        url = url_map.get(chain_name.lower())
        if not url:
            raise ValueError(f"Unsupported chain: {chain_name}. Available: {list(url_map.keys())}")
        
        if "infura.io/v3/" in url and not url.endswith("/YOUR_KEY"):
            logger.warning("Using Infura RPC - ensure API key is configured")
        
        return url
    
    def _initialize_web3(self) -> Web3:
        """Initialize Web3 connection with error handling"""
        try:
            w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            
            # Test connection
            if not w3.is_connected():
                raise ConnectionError(f"Failed to connect to {self.chain_name} RPC")
            
            logger.info(f"Connected to {self.chain_name}. Chain ID: {w3.eth.chain_id}")
            logger.info(f"Latest block: {w3.eth.block_number}")
            
            return w3
        except Exception as e:
            logger.error(f"Failed to initialize Web3: {e}")
            raise
    
    def _initialize_firestore(self) -> firestore.Client:
        """Initialize Firebase Firestore client"""
        try:
            # Initialize Firebase if not already initialized
            if not firebase_admin._apps:
                cred = credentials.Certificate(firebase_config.SERVICE_ACCOUNT_PATH)
                firebase_admin.initialize_app(cred, {
                    'projectId': firebase_config.PROJECT_ID,
                    'databaseURL': firebase_config.DATABASE_URL
                })
            
            db = firestore.client()
            logger.info(f"Firestore initialized for project: {firebase_config.PROJECT_ID}")
            return db
        except Exception as e:
            logger.error(f"Failed to initialize Firestore: {e}")
            raise
    
    def _load_dao_patterns(self) -> Dict:
        """Load known DAO contract patterns and ABIs"""
        patterns = {
            "gnosis_safe": {
                "factory_addresses": [
                    "0x76e2cfc1f5fa8f6a5b3fc4c8f4788f0116861f9b",  # Gnosis Safe Factory
                    "0xa6b71e26c5e0845f74c812102ca7114b6a896ab2"   # Gnosis Safe Proxy Factory
                ],
                "abi": self._load_abi("gnosis_safe")
            },
            "governance_token": {
                "patterns": dao_detection_config.TOKEN_CONTRACT_PATTERNS,
                "abi": self._load_abi("erc20")
            },
            "vesting_schedule": {
                "abi": self._load_abi("vesting")
            }
        }
        return patterns
    
    def _load_abi(self, abi_type: str) -> List[Dict]:
        """Load contract ABI from local storage or defaults"""
        # For production, these should be in separate JSON files
        abi_map = {
            "erc20": [
                {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
                {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "owner", "outputs": [{"name": "", "type": "address"}], "type": "function"}
            ],
            "gnosis_safe": [
                {"constant": True, "inputs": [], "name": "getOwners", "outputs": [{"name": "", "type": "address[]"}], "type": "function"},
                {"constant": True, "inputs": [], "name": "getThreshold", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
            ]
        }
        
        return abi_map.get(abi_type, [])
    
    def _detect_new_dao(self, contract_address: str) -> Optional[Dict]:
        """
        Analyze contract bytecode for DAO patterns
        
        Args:
            contract_address: Ethereum address to analyze
            
        Returns:
            DAO metadata if detected, None otherwise
        """
        try:
            # Basic validation
            if not Web3.is_address(contract_address):
                logger.warning(f"Invalid address: {contract_address}")
                return None
            
            normalized_address = Web3.to_checksum_address(contract_address)
            
            # Check if already indexed
            if self._is_already_indexed(normalized_address):
                logger.debug(f"Address already indexed: {normalized_address}")
                return None
            
            # Get contract bytecode
            bytecode = self.w3.eth.get_code(normalized_address).hex()
            
            if bytecode == '0x' or bytecode == '0x0':
                logger.debug(f"No contract at address: {normalized_address}")
                return None
            
            # Check for DAO patterns
            dao_metadata = {}
            
            # Pattern 1: Check if it's a token with governance
            if self._is_governance_token(normalized_address):
                dao_metadata.update(self._analyze_governance_token(normalized_address))
            
            # Pattern 2: Check for multi-sig treasury
            if self._