class _BookNode:
    __slots__ = ("book", "next")

    def __init__(self, book):
        self.book = book
        self.next = None


class BookLinkedList:
    def __init__(self, books=()):
        self.head = None
        self.tail = None
        self._size = 0
        for book in books:
            self.append(book)

    def append(self, book):
        node = _BookNode(book)
        if self.tail is None:
            self.head = node
        else:
            self.tail.next = node
        self.tail = node
        self._size += 1

    def find(self, book_id):
        return next(
            (book for book in self if book.book_id == book_id),
            None,
        )

    def remove(self, book_id):
        previous = None
        current = self.head
        while current is not None:
            if current.book.book_id == book_id:
                if previous is None:
                    self.head = current.next
                else:
                    previous.next = current.next
                if current is self.tail:
                    self.tail = previous
                self._size -= 1
                return True
            previous, current = current, current.next
        return False

    def __iter__(self):
        current = self.head
        while current is not None:
            yield current.book
            current = current.next

    def __len__(self):
        return self._size

    def __getitem__(self, index):
        if isinstance(index, slice):
            return list(self)[index]
        if index < 0:
            index += self._size
        if index < 0 or index >= self._size:
            raise IndexError("Book index out of range.")
        current = self.head
        for _ in range(index):
            current = current.next
        return current.book

    def __eq__(self, other):
        try:
            return list(self) == list(other)
        except TypeError:
            return NotImplemented


class _GenreNode:
    __slots__ = ("key", "name", "left", "right", "height")

    def __init__(self, name):
        self.key = name.casefold()
        self.name = name
        self.left = None
        self.right = None
        self.height = 1


class GenreTree:
    def __init__(self, names=()):
        self.root = None
        for name in names:
            self.insert(name)

    @staticmethod
    def _height(node):
        return node.height if node else 0

    @classmethod
    def _update_height(cls, node):
        node.height = 1 + max(cls._height(node.left), cls._height(node.right))

    @classmethod
    def _rotate_right(cls, root):
        pivot = root.left
        root.left = pivot.right
        pivot.right = root
        cls._update_height(root)
        cls._update_height(pivot)
        return pivot

    @classmethod
    def _rotate_left(cls, root):
        pivot = root.right
        root.right = pivot.left
        pivot.left = root
        cls._update_height(root)
        cls._update_height(pivot)
        return pivot

    @classmethod
    def _insert(cls, node, name):
        if node is None:
            return _GenreNode(name)
        key = name.casefold()
        if key == node.key:
            return node
        if key < node.key:
            node.left = cls._insert(node.left, name)
        else:
            node.right = cls._insert(node.right, name)

        cls._update_height(node)
        balance = cls._height(node.left) - cls._height(node.right)
        if balance > 1:
            if key > node.left.key:
                node.left = cls._rotate_left(node.left)
            return cls._rotate_right(node)
        if balance < -1:
            if key < node.right.key:
                node.right = cls._rotate_right(node.right)
            return cls._rotate_left(node)
        return node

    def insert(self, name):
        cleaned = (name or "").strip()
        if cleaned:
            self.root = self._insert(self.root, cleaned)

    def contains(self, name):
        key = (name or "").strip().casefold()
        node = self.root
        while node is not None:
            if key == node.key:
                return True
            node = node.left if key < node.key else node.right
        return False

    def in_order(self):
        names = []
        stack = []
        node = self.root
        while stack or node is not None:
            while node is not None:
                stack.append(node)
                node = node.left
            node = stack.pop()
            names.append(node.name)
            node = node.right
        return names
