from bcfcc import AddGP

class Card(AddGP):
    def __init__(self, label, cost):
        super().__init__(label, cost, None)
        self._tier = None

    def sell(self):
        super().__call__(self.cost)

    def full(self):
        pass

    def direct(self):
