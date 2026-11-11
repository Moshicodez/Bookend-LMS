from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
WIDTH, HEIGHT = 5400, 3450
WHITE = "#FFFFFF"
INK = "#252A25"
MUTED = "#666C63"
GREEN = "#435B43"
GREEN_LIGHT = "#EDF2EB"
TERRA = "#BD7657"
TERRA_LIGHT = "#F8EEE9"
BORDER = "#DADFD6"
PANEL = "#F8F9F6"


def font(name, size):
    return ImageFont.truetype(fr"C:\Windows\Fonts\{name}", size)


FONTS = {
    "title": font("georgiab.ttf", 76),
    "subtitle": font("segoeui.ttf", 31),
    "section": font("segoeuib.ttf", 34),
    "class": font("segoeuib.ttf", 38),
    "stereotype": font("segoeuii.ttf", 23),
    "description": font("segoeui.ttf", 25),
    "body": font("segoeui.ttf", 27),
    "body_bold": font("segoeuib.ttf", 27),
    "small": font("segoeui.ttf", 23),
    "relation": font("segoeuib.ttf", 25),
    "footer": font("segoeui.ttf", 22),
}

image = Image.new("RGB", (WIDTH, HEIGHT), WHITE)
draw = ImageDraw.Draw(image)


def rounded_box(box, fill=WHITE, outline=BORDER, radius=22, width=3):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def text(x, y, value, style="body", fill=INK):
    draw.text((x, y), value, font=FONTS[style], fill=fill)


def wrapped_lines(value, width, font_obj):
    approx = max(15, int(width / (font_obj.size * 0.53)))
    return textwrap.wrap(value, width=approx, break_long_words=False)


def class_card(x, y, w, h, name, description, fields, methods=(), stereotype=None,
               accent=GREEN, fill=WHITE):
    rounded_box((x, y, x + w, y + h), fill=fill, outline=BORDER, radius=24, width=3)
    header_h = 78
    draw.rounded_rectangle((x, y, x + w, y + header_h + 18), radius=24, fill=accent)
    draw.rectangle((x, y + header_h, x + w, y + header_h + 18), fill=accent)
    if stereotype:
        text(x + 24, y + 13, stereotype, "stereotype", "#E9F0E7")
        text(x + 24, y + 37, name, "class", WHITE)
    else:
        text(x + 24, y + 17, name, "class", WHITE)
    yy = y + header_h + 33
    for line in wrapped_lines(description, w - 48, FONTS["description"]):
        text(x + 24, yy, line, "description", MUTED)
        yy += 32
    yy += 9
    draw.line((x + 20, yy, x + w - 20, yy), fill=BORDER, width=2)
    yy += 14
    for field in fields:
        lines = wrapped_lines(field, w - 48, FONTS["body"])
        for line in lines:
            text(x + 24, yy, line, "body")
            yy += 34
    if methods:
        yy += 8
        draw.line((x + 20, yy, x + w - 20, yy), fill=BORDER, width=2)
        yy += 12
        for method in methods:
            text(x + 24, yy, method, "small", GREEN)
            yy += 30


def line(points, color=GREEN, width=4):
    draw.line(points, fill=color, width=width, joint="curve")


def inheritance(child_center, child_top, parent_center, parent_bottom):
    # UML generalization: the open triangle points to the parent class.
    mid_y = (child_top + parent_bottom) // 2
    line([(child_center, child_top), (child_center, mid_y), (parent_center, mid_y),
          (parent_center, parent_bottom + 16)], color=GREEN, width=4)
    draw.polygon(
        [
            (parent_center, parent_bottom),
            (parent_center - 15, parent_bottom + 20),
            (parent_center + 15, parent_bottom + 20),
        ],
        fill=WHITE,
        outline=GREEN,
    )


def chip(x, y, w, label, detail):
    rounded_box((x, y, x + w, y + 118), fill=WHITE, outline=BORDER, radius=18, width=2)
    text(x + 18, y + 15, label, "relation", GREEN)
    text(x + 18, y + 58, detail, "small", MUTED)


# Title and identity
text(110, 56, "BOOKEND  |  UML CLASS DIAGRAM", "title", GREEN)
text(
    114,
    153,
    "Library lending system  ·  Core business objects and the records that persist them",
    "subtitle",
    MUTED,
)
draw.line((110, 222, WIDTH - 110, 222), fill=BORDER, width=3)

# Core domain model
rounded_box((90, 260, WIDTH - 90, 1745), fill="#FCFDFC", outline=BORDER, radius=30, width=3)
text(125, 286, "CORE DOMAIN  |  Rules and concepts the application works with", "section", GREEN)

# Generalization connectors (drawn before the cards).
inheritance(405, 915, 490, 755)
inheritance(1095, 915, 490, 755)
inheritance(1815, 915, 1980, 790)
inheritance(2505, 915, 1980, 790)
inheritance(4085, 915, 4260, 690)
inheritance(4760, 915, 4260, 690)

# User and book families
class_card(
    120, 395, 740, 360, "User",
    "Shared account rules and identity. Abstract: users sign in as a specific role.",
    ["user_id · email · username · active"],
    ["check_pass() · activate() · deactivate()"],
    stereotype="«abstract»",
)
class_card(
    120, 915, 570, 360, "Patron",
    "Library member who borrows and saves books.",
    ["Inherits account details", "Has an active-loan limit"],
    ["borrow · return · review · favorite"],
)
class_card(
    810, 915, 570, 360, "Librarian",
    "Staff account for catalog and library operations.",
    ["Inherits account details", "Manages members and loans"],
    ["catalog · fees · genres · notices"],
)

class_card(
    1580, 395, 800, 395, "Book",
    "A catalog title with tracked physical copies and availability.",
    ["book_id · title · author · genre", "total · available · on-loan · reserved copies"],
    ["borrow() · return_book() · archive()"],
)
class_card(
    1510, 915, 610, 360, "NewReleaseBook",
    "A book with a shorter lending period.",
    ["Inherits book details", "Loan period: 7 days"],
    ["Uses standard borrow / return rules"],
)
class_card(
    2240, 915, 610, 360, "ReferenceBook",
    "A book available for reading in the library only.",
    ["Inherits book details", "Not borrowable for take-home use"],
    ["can_borrow() → no"],
)

# Circulation and fees
class_card(
    3030, 395, 790, 445, "Loan",
    "One borrowing event connecting a member to a book.",
    ["loan_id · borrowed_at · due_date · returned_at", "patron_id → Patron · book_id → Book"],
    ["mark_returned() · mark_lost()", "outstanding() · fee_breakdown()"],
)
class_card(
    3030, 915, 790, 360, "Reservation",
    "A place in the queue when all borrowable copies are in use.",
    ["patron_id → Patron · book_id → Book", "status: waiting · ready · fulfilled · cancelled"],
    ["Waiting reservations promote FIFO"],
)
class_card(
    3910, 395, 780, 295, "Fee",
    "A charge associated with a loan. Abstract fee calculation.",
    ["paid · amount(loan, current_date)"],
    ["outstanding()"],
    stereotype="«abstract»",
    accent=TERRA,
)
class_card(
    3910, 915, 570, 360, "LateFee",
    "Accumulates when a book is returned after its due date.",
    ["Calculated per day overdue", "Waived for a lost book"],
    ["amount(loan, date)"],
    accent=TERRA,
    fill=TERRA_LIGHT,
)
class_card(
    4560, 915, 570, 360, "LossFee",
    "Fixed charge when a loan is marked as a lost book.",
    ["Fixed amount", "Recorded on the loan"],
    ["amount(loan, date)"],
    accent=TERRA,
    fill=TERRA_LIGHT,
)

# Plain-language relationship guide: avoids crossing association lines over classes.
text(125, 1330, "HOW THE MAIN RELATIONSHIPS WORK", "section", GREEN)
chip(125, 1382, 790, "1 Patron  →  0..* Loans", "A member can have multiple loan records.")
chip(950, 1382, 790, "1 Book  →  0..* Loans", "A title can appear in many loans over time.")
chip(1775, 1382, 790, "1 Patron  →  0..* Reservations", "A member may queue for several titles.")
chip(2600, 1382, 790, "1 Book  →  0..* Reservations", "Reservations queue by book, first in first out.")
chip(3425, 1382, 790, "1 Loan  ◆  0..2 Fee types", "A loan may have a late fee and/or loss fee.")

# Persistence model
rounded_box((90, 1780, WIDTH - 90, 3235), fill=PANEL, outline=BORDER, radius=30, width=3)
text(125, 1808, "DATABASE RECORDS  |  SQLAlchemy classes that store the application data", "section", GREEN)
text(
    125,
    1864,
    "Repositories translate between these stored records and the domain objects above. Record classes are not domain subclasses.",
    "description",
    MUTED,
)

record_w, record_h = 900, 340
lefts = [125, 1160, 2195, 3230, 4265]
row1_y, row2_y = 1950, 2380
records = [
    ("UserRecord", "users", "Accounts: email, username, role, active status.", GREEN),
    ("BookRecord", "books", "Catalog details, book kind, copy count, archive state.", GREEN),
    ("LoanRecord", "loans", "Borrowing dates, member/title IDs, return and lost state.", GREEN),
    ("ReservationRecord", "reservations", "Member/title IDs, queue status, created time.", GREEN),
    ("GenreRecord", "genres", "Unique genre names used to organize catalog books.", GREEN),
    ("FavoriteRecord", "favorites", "Saved member-to-book pairs.", TERRA),
    ("BasketRecord", "basket_items", "Books a member has placed in their borrow basket.", TERRA),
    ("ReviewRecord", "reviews", "Member rating and comment for a book.", TERRA),
    ("FeePaymentRecord", "fee_payments", "Payment, receipt and confirmation details for a loan.", TERRA),
    ("NotificationRecord", "notifications", "In-app messages, read state and recipient.", TERRA),
]
for index, (name, table, description, accent) in enumerate(records):
    x = lefts[index % 5]
    y = row1_y if index < 5 else row2_y
    rounded_box((x, y, x + record_w, y + record_h), fill=WHITE, outline=BORDER, radius=22, width=3)
    draw.rounded_rectangle((x, y, x + record_w, y + 83), radius=22, fill=accent)
    draw.rectangle((x, y + 60, x + record_w, y + 83), fill=accent)
    text(x + 22, y + 10, name, "class", WHITE)
    text(x + 24, y + 98, f"Table: {table}", "body_bold", INK)
    yy = y + 147
    for row in wrapped_lines(description, record_w - 48, FONTS["body"]):
        text(x + 24, yy, row, "body", MUTED)
        yy += 36

# Key and source notes
draw.line((125, 2848, WIDTH - 125, 2848), fill=BORDER, width=2)
text(125, 2883, "UML key", "body_bold", GREEN)
draw.line((280, 2902, 400, 2902), fill=GREEN, width=4)
draw.polygon([(340, 2889), (327, 2908), (353, 2908)], fill=WHITE, outline=GREEN)
text(420, 2884, "Inheritance (open triangle points to the parent class)", "small", MUTED)
text(1530, 2884, "◆  Composition: fee types belong to a loan.", "small", MUTED)
text(2840, 2884, "1 / 0..*  One-to-many relationship counts.", "small", MUTED)

text(
    125,
    3025,
    "Scope: core domain classes and the main persistence records. Routes, services and repositories are omitted to keep the model readable.",
    "footer",
    MUTED,
)
text(
    125,
    3070,
    "Based on Bookend-LMS backend/app/models and backend/app/repositories.",
    "footer",
    MUTED,
)
text(125, 3150, "BOOKEND  ·  WHITE BACKGROUND  ·  PRINT-FRIENDLY LANDSCAPE", "footer", GREEN)

# Export a high-resolution PNG and a landscape PDF at 300 dpi.
png_path = ROOT / "bookend_uml_class_diagram.png"
pdf_path = ROOT / "bookend_uml_class_diagram.pdf"
image.save(png_path, dpi=(300, 300), optimize=True)
image.save(pdf_path, "PDF", resolution=300, title="Bookend UML Class Diagram")
print(f"Created {png_path} ({WIDTH} x {HEIGHT})")
print(f"Created {pdf_path}")
