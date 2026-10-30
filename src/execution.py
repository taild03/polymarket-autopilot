"""Conservative paper fills against the five nearest CLOB price levels."""
from dataclasses import replace


def cost_for_quantity(levels, quantity, limit=None):
    remaining, cost = quantity, 0.0
    for price, size in levels:
        if limit is not None and price > limit:
            break
        take = min(remaining, size)
        cost += take * price
        remaining -= take
        if remaining <= 1e-8:
            return cost
    return None


class ExecutionBooks:
    def __init__(self, client, contracts):
        self.client = client
        self.contracts = {c.market_id: c for c in contracts}
        self.cache = {}

    def book(self, market_id, side="BUY_YES"):
        contract = self.contracts.get(market_id)
        if contract is None or contract.closed:
            return None
        token = contract.no_token_id if side == "BUY_NO" else contract.yes_token_id
        if not token:
            return None
        if token not in self.cache:
            self.cache[token] = self.client.fetch_clob_book_top(token)
        return self.cache[token]

    def validate(self, signal, decision):
        if not decision.approved:
            return decision
        ids = signal.leg_market_ids if signal.side == "BUY_BUNDLE" else [signal.market_id]
        reason, total = "", 0.0
        if not ids:
            reason = "MISSING_BUNDLE_LEGS"
        for mid in ids:
            book = self.book(mid, signal.side)
            if book is None:
                reason = "CLOB_UNAVAILABLE"
                break
            if book["bid_depth_usd"] < decision.recommended_size_usdc / len(ids):
                reason = "INSUFFICIENT_BID_DEPTH"
                break
            if signal.order_type == "LIMIT_MAKER":
                tick = book.get("tick_size", self.client.config.tick_size)
                if abs(signal.entry_price / tick - round(signal.entry_price / tick)) > 1e-7:
                    reason = "INVALID_TICK_SIZE"
                    break
                if decision.shares_qty < book.get("min_order_size", 0):
                    reason = "BELOW_MINIMUM_SHARES"
                    break
                if not book["asks"] or book["best_ask"] <= signal.entry_price:
                    reason = "MAKER_WOULD_CROSS"
                break
            cost = cost_for_quantity(book["asks"], decision.shares_qty)
            if cost is None:
                reason = "INSUFFICIENT_ASK_DEPTH"
                break
            total += cost
        if signal.order_type != "LIMIT_MAKER" and not reason:
            total += decision.shares_qty * len(ids) * self.client.config.taker_fee_bps / 10000
            if total > decision.recommended_size_usdc + 1e-8:
                reason = "PRICE_MOVED_OR_FEE_EXCEEDS_BUDGET"
        if reason:
            return replace(decision, approved=False, recommended_size_usdc=0.0,
                           shares_qty=0.0, reject_reason=reason)
        return replace(decision, risk_checks_passed=decision.risk_checks_passed + ["CLOB_DEPTH_OK"])
