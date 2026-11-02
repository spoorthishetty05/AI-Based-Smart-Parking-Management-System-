
"""
Central Configuration Module for AI-Based Smart Parking System.
Provides environment-aware settings for Flask, MongoDB, Simulation, and Security.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    """Base application configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'smart-parking-ai-secret-2026')
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017/')
    MONGO_DB_NAME = os.environ.get('MONGO_DB_NAME', 'smart_parking')
    SIMULATION_DEFAULT_OFFSET = int(os.environ.get('SIMULATION_OFFSET', 0))
    DEFAULT_GRACE_PERIOD_MINUTES = 15
    DEFAULT_CAR_PENALTY = 60.0
    DEFAULT_BIKE_PENALTY = 30.0
    DEFAULT_OTHER_PENALTY = 80.0
    DEBUG = False
    TESTING = False

class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True

class TestingConfig(Config):
    """Testing environment configuration."""
    TESTING = True
    DEBUG = True
    MONGO_DB_NAME = os.environ.get('TEST_MONGO_DB_NAME', 'smart_parking')

class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False
    TESTING = False

config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
