-- Migration 0001: init extensions

-- Enable pgcrypto for UUID generation and cryptographic functions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
