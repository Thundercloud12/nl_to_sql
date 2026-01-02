"""
Agent Authentication

Secure token-based authentication for agent-service communication.
Uses HMAC-based tokens with time-limited validity.
"""

import os
import hmac
import hashlib
import secrets
import base64
import json
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any


# Token validity period
TOKEN_VALIDITY_HOURS = 24
SIGNATURE_ALGORITHM = "sha256"


def generate_agent_credentials() -> Tuple[str, str, str]:
    """
    Generate a new set of agent credentials.
    
    Returns:
        Tuple of (agent_id, agent_token, agent_secret)
    """
    agent_id = f"agent_{secrets.token_hex(12)}"
    agent_token = f"tok_{secrets.token_hex(24)}"
    agent_secret = secrets.token_hex(32)
    
    return agent_id, agent_token, agent_secret


def generate_agent_token(agent_id: str, agent_secret: str, validity_hours: int = TOKEN_VALIDITY_HOURS) -> str:
    """
    Generate a time-limited access token for agent authentication.
    
    Args:
        agent_id: The agent's unique identifier
        agent_secret: The agent's secret key
        validity_hours: How long the token is valid
        
    Returns:
        Base64-encoded signed token
    """
    expiry = datetime.utcnow() + timedelta(hours=validity_hours)
    
    payload = {
        "agent_id": agent_id,
        "exp": expiry.isoformat(),
        "iat": datetime.utcnow().isoformat(),
        "nonce": secrets.token_hex(8)
    }
    
    payload_json = json.dumps(payload, sort_keys=True)
    payload_bytes = payload_json.encode('utf-8')
    
    # Create HMAC signature
    signature = hmac.new(
        agent_secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).digest()
    
    # Combine payload and signature
    token_data = payload_bytes + b'.' + signature
    
    return base64.urlsafe_b64encode(token_data).decode('utf-8')


def validate_agent_token(token: str, agent_id: str, agent_secret: str) -> Tuple[bool, Optional[str]]:
    """
    Validate an agent access token.
    
    Args:
        token: The token to validate
        agent_id: Expected agent ID
        agent_secret: The agent's secret key
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Decode token
        token_data = base64.urlsafe_b64decode(token.encode('utf-8'))
        
        # Split payload and signature
        parts = token_data.rsplit(b'.', 1)
        if len(parts) != 2:
            return False, "Invalid token format"
        
        payload_bytes, received_signature = parts
        
        # Verify signature
        expected_signature = hmac.new(
            agent_secret.encode('utf-8'),
            payload_bytes,
            hashlib.sha256
        ).digest()
        
        if not hmac.compare_digest(received_signature, expected_signature):
            return False, "Invalid signature"
        
        # Parse and validate payload
        payload = json.loads(payload_bytes.decode('utf-8'))
        
        # Check agent ID
        if payload.get("agent_id") != agent_id:
            return False, "Agent ID mismatch"
        
        # Check expiry
        expiry = datetime.fromisoformat(payload["exp"])
        if datetime.utcnow() > expiry:
            return False, "Token expired"
        
        return True, None
        
    except Exception as e:
        return False, f"Token validation error: {str(e)}"


def sign_payload(payload: Dict[str, Any], agent_secret: str) -> str:
    """
    Sign a payload with the agent secret.
    
    Args:
        payload: Dictionary payload to sign
        agent_secret: The agent's secret key
        
    Returns:
        Base64-encoded signature
    """
    payload_json = json.dumps(payload, sort_keys=True, default=str)
    
    signature = hmac.new(
        agent_secret.encode('utf-8'),
        payload_json.encode('utf-8'),
        hashlib.sha256
    ).digest()
    
    return base64.urlsafe_b64encode(signature).decode('utf-8')


def verify_payload_signature(payload: Dict[str, Any], signature: str, agent_secret: str) -> bool:
    """
    Verify a payload signature.
    
    Args:
        payload: Dictionary payload that was signed
        signature: Base64-encoded signature to verify
        agent_secret: The agent's secret key
        
    Returns:
        True if signature is valid
    """
    try:
        expected_signature = sign_payload(payload, agent_secret)
        return hmac.compare_digest(signature, expected_signature)
    except Exception:
        return False


class AgentAuthenticator:
    """
    Handles agent authentication and message signing.
    """
    
    def __init__(self, agent_id: str, agent_secret: str):
        self.agent_id = agent_id
        self.agent_secret = agent_secret
        self._current_token: Optional[str] = None
        self._token_expiry: Optional[datetime] = None
    
    def get_token(self, force_refresh: bool = False) -> str:
        """
        Get a valid access token, refreshing if necessary.
        
        Args:
            force_refresh: Force generation of a new token
            
        Returns:
            Valid access token
        """
        # Check if current token is still valid
        if not force_refresh and self._current_token and self._token_expiry:
            # Refresh if less than 1 hour remaining
            if datetime.utcnow() < self._token_expiry - timedelta(hours=1):
                return self._current_token
        
        # Generate new token
        self._current_token = generate_agent_token(self.agent_id, self.agent_secret)
        self._token_expiry = datetime.utcnow() + timedelta(hours=TOKEN_VALIDITY_HOURS)
        
        return self._current_token
    
    def sign_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sign a request payload for secure transmission.
        
        Args:
            payload: Request payload
            
        Returns:
            Payload with added authentication headers
        """
        timestamp = datetime.utcnow().isoformat()
        
        # Add metadata to payload
        signed_payload = {
            **payload,
            "_agent_id": self.agent_id,
            "_timestamp": timestamp,
            "_nonce": secrets.token_hex(8)
        }
        
        # Generate signature
        signature = sign_payload(signed_payload, self.agent_secret)
        
        return {
            "payload": signed_payload,
            "signature": signature,
            "token": self.get_token()
        }
    
    def verify_request(self, request_data: Dict[str, Any]) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Verify an incoming signed request.
        
        Args:
            request_data: The complete request with payload, signature, and token
            
        Returns:
            Tuple of (is_valid, error_message, payload)
        """
        try:
            payload = request_data.get("payload")
            signature = request_data.get("signature")
            token = request_data.get("token")
            
            if not all([payload, signature, token]):
                return False, "Missing required fields", None
            
            # Verify token
            token_valid, token_error = validate_agent_token(token, self.agent_id, self.agent_secret)
            if not token_valid:
                return False, token_error, None
            
            # Verify signature
            if not verify_payload_signature(payload, signature, self.agent_secret):
                return False, "Invalid signature", None
            
            # Verify timestamp (within 5 minutes)
            timestamp = datetime.fromisoformat(payload.get("_timestamp", "1970-01-01"))
            if abs((datetime.utcnow() - timestamp).total_seconds()) > 300:
                return False, "Request timestamp too old", None
            
            # Verify agent ID
            if payload.get("_agent_id") != self.agent_id:
                return False, "Agent ID mismatch", None
            
            return True, None, payload
            
        except Exception as e:
            return False, f"Verification error: {str(e)}", None
