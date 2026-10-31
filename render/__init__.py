"""Render a Profile in a real browser.

Importing this package must not require playwright: only render.driver
imports it, and it degrades to available() == False when absent.
"""
