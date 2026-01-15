# QuantConnect Test Setup

This project contains test files for connecting to QuantConnect's algorithmic trading platform.

## Setup Instructions

### 1. Install Dependencies

```bash
pip install quantconnect
```

### 2. Get Your API Credentials

1. Go to [QuantConnect Account Settings](https://www.quantconnect.com/account)
2. Copy your User ID and API Token

### 3. Configure Your Credentials

Edit `test_connection.py` and replace:
- `YOUR_USER_ID` with your actual User ID
- `YOUR_API_TOKEN` with your actual API Token

Or create a `config.py` file (recommended):
```bash
cp config_template.py config.py
# Then edit config.py with your credentials
```

### 4. Run the Test

```bash
python test_connection.py
```

## Files

- `test_connection.py` - Main test script to verify QuantConnect API connection
- `config_template.py` - Template for storing credentials (copy to config.py)
- `Main.py` - Main entry point for your algorithms
- `.gitignore` - Prevents committing sensitive credentials

## Troubleshooting

If you encounter issues:

1. **Module not found**: Install the package with `pip install quantconnect`
2. **Authentication failed**: Double-check your User ID and API Token
3. **Connection timeout**: Check your internet connection

## Next Steps

Once connected successfully, you can:
- Create and backtest algorithms through the API
- Retrieve historical data
- Deploy live trading algorithms
- Manage your QuantConnect projects programmatically

## Resources

- [QuantConnect Documentation](https://www.quantconnect.com/docs)
- [QuantConnect API Docs](https://www.quantconnect.com/docs/v2/cloud-platform/api-reference)
- [LEAN Algorithm Framework](https://www.quantconnect.com/docs/v2/lean-cli)
