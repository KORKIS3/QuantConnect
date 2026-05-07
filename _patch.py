with open("InteractiveBrokers.py", "r", encoding="utf-8") as f:
    content = f.read()

# PATCH 1
p1_old = (
    "        except Exception as exc:\n"
    '            log.warning("[Connect] Could not sync position from IB: %s", exc)\n'
    "\n"
    "    def disconnect(self)"
)
p1_new = (
    "        except Exception as exc:\n"
    '            log.warning("[Connect] Could not sync position from IB: %s", exc)\n'
    "\n"
    "        # Subscribe to portfolio updates so _ib_position stays accurate from real fills\n"
    "        self._ib.updatePortfolioEvent += self._on_portfolio_update\n"
    "\n"
    "    def _on_portfolio_update(self, item) -> None:\n"
    '        """Called by IB on every fill - keeps _ib_position in sync with real fills."""\n'
    '        if item.contract.symbol in ("YM", "MYM"):\n'
    "            new_pos = int(item.position)\n"
    "            if new_pos != self._ib_position:\n"
    '                log.info("[PositionSync] IB fill confirmed: _ib_position %d -> %d",\n'
    "                         self._ib_position, new_pos)\n"
    "                self._ib_position = new_pos\n"
    "\n"
    "    def disconnect(self)"
)
assert p1_old in content, "P1 missing"
content = content.replace(p1_old, p1_new, 1)
print("P1 ok")

# PATCH 2 - find the comment line with em-dash dynamically
comment_line = next(l for l in content.split("\n") if "Calculate quantity" in l)
p2_old = (
    comment_line + "\n"
    "        nc = self.config.num_contracts\n"
    "        if partial_tp:\n"
    "            qty = max(1, abs(self._ib_position) // 2)\n"
    "        elif liquidate:\n"
    "            qty = abs(self._ib_position) if self._ib_position != 0 else nc\n"
    "        else:\n"
    '            if action == "BUY":\n'
    "                qty = nc + max(0, -self._ib_position)   # cover shorts + go long\n"
    "            else:\n"
    "                qty = nc + max(0, self._ib_position)     # cover longs + go short"
)
p2_new = (
    "        # Refresh position from IB before calculating qty to avoid stale estimates\n"
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
    + comment_line + "\n"
    "        nc = self.config.num_contracts\n"
    "        if partial_tp:\n"
    "            qty = max(1, abs(self._ib_position) // 2)\n"
    "        elif liquidate:\n"
    "            qty = abs(self._ib_position) if self._ib_position != 0 else nc\n"
    "        else:\n"
    '            if action == "BUY":\n'
    "                qty = nc + max(0, -self._ib_position)   # cover shorts + go long\n"
    "            else:\n"
    "                qty = nc + max(0, self._ib_position)     # cover longs + go short"
)
assert p2_old in content, "P2 missing"
content = content.replace(p2_old, p2_new, 1)
print("P2 ok")

# PATCH 3
p3_old = (
    "        # Track actual IB position so same-direction signals can be skipped\n"
    "        if liquidate:\n"
    "            self._ib_position = 0\n"
    "        elif partial_tp:\n"
    "            self._ib_position = max(0, abs(self._ib_position) - 1) * (1 if self._ib_position > 0 else -1)\n"
    '        elif action == "BUY":\n'
    "            self._ib_position = 2\n"
    '        elif action == "SELL":\n'
    "            self._ib_position = -2"
)
p3_new = (
    "        # NOTE: _ib_position is now updated by _on_portfolio_update() on fill confirmation,\n"
    "        # not here on order placement. This prevents the race condition where a partial TP\n"
    "        # order is placed but not yet filled when the next signal fires."
)
assert p3_old in content, "P3 missing"
content = content.replace(p3_old, p3_new, 1)
print("P3 ok")

with open("InteractiveBrokers.py", "w", encoding="utf-8") as f:
    f.write(content)
print("All patches applied successfully")
