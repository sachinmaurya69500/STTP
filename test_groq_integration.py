#!/usr/bin/env python3
"""
Test script to verify Groq API integration for notes generation.
"""

import asyncio
import json
import os
from pathlib import Path

# Load environment variables first
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# Import the main.py functions
from main import generate_notes_with_groq, GROQ_API_KEY, Groq

async def test_groq_integration():
    """Test the Groq notes generation functionality."""
    
    if not GROQ_API_KEY:
        print("❌ GROQ_API_KEY not set in .env file")
        print(f"   Looking for .env in: {Path.cwd()}")
        print(f"   GROQ_API_KEY value: {os.getenv('GROQ_API_KEY', 'NOT FOUND')}")
        return False
    
    if not Groq:
        print("❌ Groq library not installed. Run: pip install groq")
        return False
    
    print("✓ GROQ_API_KEY is configured")
    print("✓ Groq library is available")
    
    # Test transcript
    test_transcript = """
    Today we are discussing machine learning fundamentals. The key concept is understanding
    the relationship between bias and variance in predictive models. Bias refers to the error
    introduced by approximating a complex problem with a simpler model. Variance refers to the
    sensitivity of the model to small fluctuations in the training data.
    
    When we build a model that is too simple, it suffers from high bias - it underfits the data
    and makes systematic errors. When we build a model that is too complex, it suffers from high
    variance - it overfits the data and captures noise.
    
    The solution is regularization, which adds a penalty term to the loss function to constrain
    the model's complexity. Common regularization techniques include L1 (Lasso), L2 (Ridge), and
    dropout in neural networks. The goal is to find the sweet spot that minimizes both bias and
    variance to achieve good generalization performance on unseen data.
    """
    
    print("\n📝 Testing transcript:")
    print("-" * 50)
    print(test_transcript.strip()[:200] + "...")
    print("-" * 50)
    
    print("\n🚀 Generating notes with Groq API...")
    try:
        result = await generate_notes_with_groq(test_transcript)
        
        print("\n✅ Notes generated successfully!")
        print(f"\n📌 Title: {result.get('title', 'N/A')}")
        print(f"\n📝 Summary:\n{result.get('summary', 'N/A')}")
        
        if result.get('key_points'):
            print(f"\n🔑 Key Points:")
            for i, point in enumerate(result.get('key_points', []), 1):
                print(f"  {i}. {point}")
        
        print(f"\n🏷️  Tags: {', '.join(result.get('tags', []))}")
        
        print("\n" + "="*50)
        print("✓ Groq integration is working correctly!")
        print("="*50)
        return True
        
    except Exception as e:
        print(f"\n❌ Error generating notes: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_groq_integration())
    exit(0 if success else 1)
