"""A tiny sample module so we have real code to index and recall."""


class CartService:
    def __init__(self):
        self.items = []

    def add_item(self, sku, qty=1):
        """Add a product to the cart by SKU."""
        self.items.append({"sku": sku, "qty": qty})
        return len(self.items)

    def total_quantity(self):
        return sum(i["qty"] for i in self.items)


def apply_discount(total, code):
    """Apply a discount code to an order total."""
    table = {"WELCOME10": 0.10, "SUMMER25": 0.25}
    return total * (1 - table.get(code, 0.0))
