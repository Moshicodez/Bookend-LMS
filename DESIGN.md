# Bookend Library UI Design

## Direction

Create a welcoming, reading-focused library experience: warm paper-like surfaces,
quiet evergreen accents, editorial serif headings, and clear sans-serif controls.
The interface should feel calm and helpful rather than like a generic admin dashboard.

## Visual tokens

- Page background: warm ivory (`#f6f4ee`)
- Main surface: soft white (`#fffefa`)
- Primary text: deep charcoal green (`#252a25`)
- Muted text: gentle gray-green (`#777b70`)
- Primary action: evergreen (`#435b43`)
- Secondary accent: muted terracotta (`#bd7657`)
- Borders: soft warm gray (`#e5e3da`)
- Headings: Georgia or a similar readable serif
- Interface text: system sans-serif

## Components and behavior

- Use generous whitespace, restrained borders, and modest corner rounding.
- Keep forms narrow and readable, with visible labels and clear focus states.
- Make primary actions evergreen with strong text contrast.
- Use book-inspired details sparingly; avoid decorative clutter.
- Support narrow screens by simplifying the layout without hiding form controls.
- Preserve keyboard access, semantic HTML, and reduced-motion preferences.

## Login screen

The login view begins with only the Bookend wordmark and a large, three-dimensional
evergreen book. Give the cover visible thickness, a rounded spine, layered cream
page edges, subtle gold details, and a soft floor shadow. The book should float
gently rather than spin in place.

Activating the book swings its cover open on the spine to reveal a two-page spread.
Place the sign-in form on the right-hand page and warm Bookend branding on the
inside cover at left. Keep the interaction keyboard accessible, disable the
invitation after opening, respect reduced-motion preferences, and focus the
username field when the spread appears. On small screens, adapt to a single
readable page while keeping the form visually within the open-book experience.
