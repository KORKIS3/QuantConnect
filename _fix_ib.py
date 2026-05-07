content = open('InteractiveBrokers.py', 'r').read()

# 1. Add portfolio update callback after connect sync
old = (
    "        except Exception as exc:\n"
    "            log.warning(\"[Connect] Could not sync position from IB: %s\", exc)\n"
    "\n"
    "    def disconnect(self)"
)
new = (
    "        except Exception as exc:\n"
    "            log.warning(\"[Connect] Could not sync position from IB: %s\", exc)\n"
    "\n"
    "        # Subscribe to portfolio updates so _ib_position stays accurate from real fills\n"
    "        self._ib.updatePortfolioEvent += self._on_portfolio_update\n"
    "\n"
    "    def _on_portfolio_update(self, item) -> None:\n"
    '        """Called by IB whenever a position changes — keeps _ib_position in sync with real fills."""\n'
    '        if item.contract.symbol in ("YM", "MYM"):\n'
    "            new_pos = int(item.position)\n"
    "            if new_pos != self._ib_position:\n"
    '                log.info("[PositionSync] IB fill confirmed: _ib_position %d -> %d",\n'
    "                         self._ib_position, new_pos)\n"
    "                self._ib_position = new_pos\n"
    "\n"
    "    def disconnect(self)"
)
assert old in content, "PATCH 1 not found"
content = content.replace(old, new, 1)

# 2. Fix _place_order to refresh position from IB before calculating qty
old2 = (
    "        # Calculate quantity — driven by config.num_contracts (change once to scale up)\n"
    "        nc = self.config.num_contracts\n"
    "        if partial_tp:\n"
    "            qty = max(1, abs(self._ib_position) // 2)\n"
    "        elif liquidate:\n"
    "            qty = abs(self._ib_position) if self._ib_position != 0 else nc\n"
    "        else:\n"
    "            if action == \"BUY\":\n"
    "                qty = nc + max(0, -self._ib_position)   # cover shorts + go long\n"
    "            else:\n"
    "                qty = nc + max(0, self._ib_position)     # cover longs + go short"
)
new2 = (
    "        # Refresh position from IB before calculating qty — avoids stale estimates\n"
    "        try:\n"
    "            positions = self._ib.positions()\n"
    "            for p in positions:\n"
    '                if p.contract.symbol in ("YM", "MYM"):\n'
    "                    real_pos = int(p.position)\n"
    "                    if real_pos != self._ib_position:\n"
    '                        log.info("[PositionSync] Pre-order reconcile: _ib_position %d -> %d",\n'
    "                                 self._ib_position, real_pos)\n"
    "                        self._ib_position = real_pos\n"
    "                    break\n"
    "        except Exception as exc:\n"
    '            log.warning("[PositionSync] Could not refresh position before order: %s", exc)\n'
    "\n"
    "        # Calculate quantity — driven by config.num_contracts (change once to scale up)\n"
    "        nc = self.config.num_contracts\n"
    "        if partial_tp:\n"
    "            qty = max(1, abs(self._ib_position) // 2)\n"
    "        elif liquidate:\n"
    "            qty = abs(self._ib_position) if self._ib_position != 0 else nc\n"
    "        else:\n"
    "            if action == \"BUY\":\n"
    "                qty = nc + max(0, -self._ib_position)   # cover shorts + go long\n"
    "            else:\n"
    "                qty = nc + max(0, self._ib_position)     # cover longs + go short"
)
assert old2 in content, "PATCH 2 not found"
content = content.replace(old2, new2, 1)

# 3. Remove optimistic _ib_position updates after order placement
old3 = (
    "        # Track actual IB position so same-direction signals can be skipped\n"
    "        if liquidate:\n"
    "            self._ib_position = 0\n"
    "        elif partial_tp:\n"
    "            self._ib_position = max(0, abs(self._ib_position) - 1) * (1 if self._ib_position > 0 else -1)\n"
    "        elif action == \"BUY\":\n"
    "            self._ib_position = 2\n"
    "        elif action == \"SELL\":\n"
    "            self._ib_position = -2"
)
new3 = (
    "        # NOTE: _ib_position is now updated by _on_portfolio_update() on fill confirmation,\n"
    "        # not here on order placement. This prevents the race condition where a partial TP\n"
    "        # order is placed but not yet filled when the next signal fires."
)
assert old3 in content, "PATCH 3 not found"
content = content.replace(old3, new3, 1)

open('InteractiveBrokers.py', 'w').write(content)
print("All 3 patches applied successfully")
