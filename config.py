"""
ARBITER Protocol Configuration
Centralized configuration management with environment variables
"""
import os
from dataclasses import dataclass
from typing import Dict, List
from dotenv import load_dotenv

load_dotenv()

@dataclass
class BlockchainConfig:
    """Blockchain connection configurations"""
    ETH_RPC_URL: str = os.getenv("ETH_RPC_URL", "https://mainnet.infura.io/v3/")
    POLYGON_RPC_URL: str = os.getenv("POLYGON_RPC_URL", "https://polygon-mainnet.infura.io/v3/")
    SOLANA_RPC_URL: str = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    WS_ENABLED: bool = bool(os.getenv("WS_ENABLED", "False"))
    CHAIN_IDS: Dict[str, int] = None
    
    def __post_init__(self):
        self.CHAIN_IDS = {
            "ethereum": 1,
            "polygon": 137,
            "arbitrum": 42161,
            "optimism": 10
        }

@dataclass
class FirebaseConfig:
    """Firebase configuration with validation"""
    SERVICE_ACCOUNT_PATH: str = os.getenv("FIREBASE_SERVICE_ACCOUNT", "./serviceAccountKey.json")
    PROJECT_ID: str = os.getenv("FIREBASE_PROJECT_ID", "")
    DATABASE_URL: str = os.getenv("FIREBASE_DATABASE_URL", "")
    
    def validate(self) -> bool:
        """Validate Firebase configuration"""
        required = [self.SERVICE_ACCOUNT_PATH, self.PROJECT_ID]
        if not all(required):
            raise ValueError("Firebase configuration incomplete. Missing: SERVICE_ACCOUNT_PATH or PROJECT_ID")
        if not os.path.exists(self.SERVICE_ACCOUNT_PATH):
            raise FileNotFoundError(f"Service account file not found: {self.SERVICE_ACCOUNT_PATH}")
        return True

@dataclass
class LHIWeights:
    """Liquidity Health Index scoring weights"""
    CONCENTRATION_RISK: float = 0.30
    SLIPPAGE_PROFILE: float = 0.25
    VOLUME_VELOCITY: float = 0.20
    VOLATILITY_SCORE: float = 0.15
    DEPTH_QUALITY: float = 0.10
    
    def validate(self) -> bool:
        """Ensure weights sum to 1.0"""
        total = sum([
            self.CONCENTRATION_RISK,
            self.SLIPPAGE_PROFILE,
            self.VOLUME_VELOCITY,
            self.VOLATILITY_SCORE,
            self.DEPTH_QUALITY
        ])
        if abs(total - 1.0) > 0.001:
            raise ValueError(f"LHI weights must sum to 1.0, got {total}")
        return True

@dataclass
class DAODetectionConfig:
    """DAO detection patterns and thresholds"""
    MIN_HOLDERS: int = int(os.getenv("MIN_HOLDERS", "50"))
    MIN_TREASURY_ETH: float = float(os.getenv("MIN_TREASURY_ETH", "10.0"))
    MIN_AGE_DAYS: int = int(os.getenv("MIN_AGE_DAYS", "3"))
    TOKEN_CONTRACT_PATTERNS: List[str] = None
    
    def __post_init__(self):
        self.TOKEN_CONTRACT_PATTERNS = [
            "0x9f8f72aa9304c8b593d555f12ef6589cc3a579a2",  # MakerDAO MKR
            "0x5f98805a4e8be255a32880fdec7f6728c6568ba0",  # LUSD pattern
            # Add more known DAO token patterns
        ]

# Global configuration instances
blockchain_config = BlockchainConfig()
firebase_config = FirebaseConfig()
lhi_weights = LHIWeights()
dao_detection_config = DAODetectionConfig()

def validate_all_configs() -> bool:
    """Validate all configuration sections"""
    try:
        firebase_config.validate()
        lhi_weights.validate()
        print("✅ All configurations validated successfully")
        return True
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        return False