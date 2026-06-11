with open('InteractiveBrokers.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Change the contract resolution from MYM to YM
content = content.replace(
    'base = Future(symbol="MYM", exchange="CBOT", currency="USD")',
    'base = Future(symbol="YM", exchange="CBOT", currency="USD")'
)
content = content.replace(
    'raise RuntimeError("No MYM contract details returned by IB.")',
    'raise RuntimeError("No YM contract details returned by IB.")'
)
content = content.replace(
    'raise RuntimeError("No active (non-expired) MYM contracts found.")',
    'raise RuntimeError("No active (non-expired) YM contracts found.")'
)
content = content.replace(
    '"""Query IB for all active MYM (Micro E-mini Dow) contracts and return the front month.',
    '"""Query IB for all active YM (E-mini Dow) contracts and return the front month.'
)

# Update the docstring at top of _place_order
content = content.replace(
    '"""Submit a market order for MYM contracts.',
    '"""Submit a market order for YM contracts.'
)

# Update the comment on _contract and _order_contract
content = content.replace(
    "self._contract: Optional[Contract] = None        # YM \xe2\x80\x94 data feed",
    "self._contract: Optional[Contract] = None        # YM \xe2\x80\x94 data feed + orders"
)
content = content.replace(
    "self._order_contract: Optional[Contract] = None  # MYM \xe2\x80\x94 order execution",
    "self._order_contract: Optional[Contract] = None  # unused (orders use _contract = YM)"
)

with open('InteractiveBrokers.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done - switched from MYM to YM')
