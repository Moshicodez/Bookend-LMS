import React, { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import FlipCard from './FlipCard.jsx';
import './FlipCard.css';

/**
 * Renders a single book card inside a server-rendered [data-book-card] div.
 * The plain fallback card is kept in the markup; this island swaps it out
 * once React hydrates the element.
 */
function BookCard({ title, author, cover, url, basketAction, available, stockTotal, stockAvailable, stockBorrowed, bookKind, catalog, role, bookId, csrf, description, isFavorite }) {
  const canBorrow = available === 'true' || available === '1';
  const availabilityLabel = catalog !== 'true'
    ? 'Archived'
    : bookKind === 'reference'
      ? 'In-library use'
      : canBorrow
        ? 'Available'
        : Number(stockBorrowed) > 0
          ? 'On loan'
          : 'Unavailable';
  const isLibrarian = role === 'librarian';
  const favoriteAction = `/books/${bookId}/favorite`;
  const editUrl = `/books/${bookId}/edit`;
  const archiveAction = `/books/${bookId}/archive`;

  const front = cover ? (
    <img
      src={cover}
      alt={`Cover of ${title}`}
      style={{
        width: '100%',
        height: '100%',
        objectFit: 'contain',
        display: 'block',
        background: '#27272a',
      }}
    />
  ) : (
    <div
      className="flip-card__face--placeholder"
      style={{
        width: '100%',
        height: '100%',
        display: 'grid',
        placeItems: 'center',
        padding: '1.2rem',
        background: '#435b43',
        color: '#fffefa',
        fontFamily: '"Poppins", "Segoe UI", Arial, sans-serif',
        fontWeight: 600,
        fontSize: 'clamp(1rem, 4vw, 1.6rem)',
        lineHeight: 1.05,
        textAlign: 'center',
        textTransform: 'uppercase',
        letterSpacing: '0.02em',
      }}
      aria-hidden="true"
    >
      {title}
    </div>
  );

  const back = (
    <div className="flip-card__back-content">
      <h3 className="flip-card__title">{title}</h3>
      <p className="flip-card__author">{author}</p>
      {canBorrow ? (
        <span className="flip-card__availability">Available</span>
      ) : (
        <span className="flip-card__availability is-borrowed">{availabilityLabel}</span>
      )}
      <p className="flip-card__stock">{stockAvailable} available / {stockTotal} total</p>
      {description ? (
        <p className="flip-card__description">{description}</p>
      ) : null}
      <a className="flip-card__link" href={url}>
        View details
      </a>
      <div className="flip-card__actions">
        {role === 'patron' ? (
          <>
            <form method="post" action={favoriteAction} className="flip-card__form">
              <input type="hidden" name="csrf_token" value={csrf} />
              <input type="hidden" name="next" value={url} />
              <button type="submit" className="flip-card__button flip-card__button--secondary heart">
                {isFavorite ? 'Saved' : 'Save'}
              </button>
            </form>
            {bookKind !== 'reference' ? (
              canBorrow ? (
                <form method="post" action={basketAction} className="flip-card__form">
                  <input type="hidden" name="csrf_token" value={csrf} />
                  <input type="hidden" name="next" value={url} />
                  <button type="submit" className="flip-card__button flip-card__button--primary basket">Add to basket</button>
                </form>
              ) : (
                <button type="button" className="flip-card__button flip-card__button--primary basket" disabled>Unavailable</button>
              )
            ) : null}
          </>
        ) : isLibrarian ? (
          <>
            <a className="flip-card__button flip-card__button--primary" href={editUrl}>
              Edit
            </a>
            <form method="post" action={archiveAction} className="flip-card__form">
              <input type="hidden" name="csrf_token" value={csrf} />
              <button type="submit" className="flip-card__button flip-card__button--secondary archive">Archive</button>
            </form>
          </>
        ) : null}
      </div>
    </div>
  );

  // FlipCard itself honours prefers-reduced-motion (useReducedMotion): it
  // disables tilt, glare and hover lift, and fades instead of rotating.
  const touch =
    typeof window !== 'undefined' &&
    ('ontouchstart' in window || navigator.maxTouchPoints > 0);

  return (
    <FlipCard
      front={front}
      back={back}
      axis="y"
      flipOnClick
      draggable
      dragDistance={0}
      tilt={!touch}
      tiltMax={12}
      glare={!touch}
      glareOpacity={0.22}
      hoverScale={touch ? 1 : 1.03}
      perspective={1100}
      stiffness={170}
      damping={20}
      width={170}
      radius={6}
      background="#27272a"
      color="#f5f5f5"
      shadow
      shadowColor="#000000"
      shadowOpacity={0.45}
      ariaLabel={`Flip card for ${title}`}
      className={touch ? 'flip-card--touch' : ''}
    />
  );
}

function mountCards() {
  const cards = document.querySelectorAll('[data-book-card]');
  if (!cards.length) return;
  cards.forEach(el => {
    if (el.dataset.bookCardMounted === 'true') return;
    el.dataset.bookCardMounted = 'true';
    const title = el.dataset.title || '';
    const author = el.dataset.author || '';
    const cover = el.dataset.cover || '';
    const url = el.dataset.url || '#';
    const basketAction = el.dataset.basketAction || '';
    const available = el.dataset.available || 'false';
    const stockTotal = el.dataset.stockTotal || '0';
    const stockAvailable = el.dataset.stockAvailable || '0';
    const stockBorrowed = el.dataset.stockBorrowed || '0';
    const bookKind = el.dataset.bookKind || 'standard';
    const catalog = el.dataset.bookCatalog || 'true';
    const role = el.dataset.role || '';
    const bookId = el.dataset.bookId || '';
    const csrf = el.dataset.csrf || '';
    const description = el.dataset.description || '';
    const isFavorite = el.dataset.favorite === 'true';
    createRoot(el).render(
      <StrictMode>
        <BookCard
          title={title}
          author={author}
          cover={cover}
          url={url}
          basketAction={basketAction}
          available={available}
          stockTotal={stockTotal}
          stockAvailable={stockAvailable}
          stockBorrowed={stockBorrowed}
          bookKind={bookKind}
          catalog={catalog}
          role={role}
          bookId={bookId}
          csrf={csrf}
          description={description}
          isFavorite={isFavorite}
        />
      </StrictMode>
    );
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', mountCards);
} else {
  mountCards();
}