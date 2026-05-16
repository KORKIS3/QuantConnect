# P/L Calculation - Industry Standard Formula

## Source
Research from quantstrategy.io and StackExchange (May 14, 2026)

## Formula
```
Gross P/L = (Exit Price – Entry Price) × Multiplier × Number of Contracts
```

## Key Rules

### For Multiple Contracts
When trading 2 contracts and closing them at DIFFERENT prices:
- **CORRECT**: Sum each contract's P/L separately
- **WRONG**: Average the exit prices then calculate

### Example
Entry: Buy 2 contracts @ 50000
Exit: Sell 1 @ 50050 (partial TP), Sell 1 @ 50100 (final exit)

**CORRECT Calculation:**
- Contract 1: (50050 - 50000) = +50 pts
- Contract 2: (50100 - 50000) = +100 pts
- **Total: +150 pts**

**WRONG Calculation (averaging):**
- Average exit: (50050 + 50100) / 2 = 50075
- Total: (50075 - 50000) × 2 = +150 pts
- (This example happens to match, but fails when contracts close at very different prices)

### Implementation for Partial TP
When partial TP is taken:
1. Close 1 contract immediately, record P/L
2. Stay in position with remaining 1 contract
3. When final exit occurs, close remaining contract and record its P/L
4. Total P/L = sum of both individual contract P/Ls

### Code Pattern
```python
# When partial TP taken
if pos == 1:
    session_pl += (close - entry_price)  # 1 contract profit
else:
    session_pl += (entry_price - close)  # 1 contract profit
partial_taken = True
# STAY IN POSITION - do not liquidate

# When final exit occurs
if partial_taken:
    # Close remaining 1 contract
    if pos == 1:
        session_pl += (close - entry_price)  # remaining contract
    else:
        session_pl += (entry_price - close)  # remaining contract
else:
    # Close both contracts
    if pos == 1:
        session_pl += 2 * (close - entry_price)
    else:
        session_pl += 2 * (entry_price - close)
```

## Critical Insight
The averaging method can mask errors and produce incorrect results, especially when:
- Contracts close at significantly different prices
- Slippage varies between exits
- Partial TP is taken far from final exit price

Always calculate per-contract P/L and sum them.
