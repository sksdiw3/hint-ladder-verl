class ActiveTokenBudget:
    def __init__(self, limit=None, *, used=0):
        if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0):
            raise ValueError("active-token budget must be a positive integer or null")
        if isinstance(used, bool) or not isinstance(used, int) or used < 0:
            raise ValueError("used tokens must be a nonnegative integer")
        self.limit, self.used = limit, used

    def add(self, count):
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise ValueError("token count must be a nonnegative integer")
        self.used += count

    @property
    def exhausted(self):
        return self.limit is not None and self.used >= self.limit

    def to_dict(self):
        return {"limit": self.limit, "used": self.used, "exhausted": self.exhausted,
                "overshoot": max(0, self.used - self.limit) if self.limit is not None else 0}
