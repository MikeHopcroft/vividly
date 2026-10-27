const LETTER_IDS = [
  'logo-v1',
  'logo-i1',
  'logo-v2',
  'logo-i2',
  'logo-d',
  'logo-l',
  'logo-y',
];
const DOT_IDS = ['logo-i1-dot', 'logo-i2-dot'];
const ALL_LOGO_IDS = [...LETTER_IDS, ...DOT_IDS];
const LETTER_DURATION_MS = 700;
const LETTER_STAGGER_MS = 90;
const DOT_DURATION_MS = 640;
const FIRST_DOT_DELAY_MS =
  LETTER_DURATION_MS + (LETTER_IDS.length - 1) * LETTER_STAGGER_MS - DOT_DURATION_MS;

export function animateLogo(logo) {
  cancelLogoAnimation(logo);

  LETTER_IDS.forEach((id, index) => {
    logo.querySelector(`#${id}`).animate(
      [
        { transform: 'translateX(560px)', opacity: 0 },
        { transform: 'translateX(0)', opacity: 1 },
      ],
      {
        duration: LETTER_DURATION_MS,
        delay: index * LETTER_STAGGER_MS,
        easing: 'cubic-bezier(.16, 1, .3, 1)',
        fill: 'both',
      }
    );
  });

  DOT_IDS.forEach((id, index) => {
    logo.querySelector(`#${id}`).animate(
      [
        { transform: 'translateY(-520px)', opacity: 0, offset: 0 },
        { transform: 'translateY(-180px)', opacity: 1, offset: 0.35 },
        { transform: 'translateY(0)', opacity: 1, offset: 0.72 },
        { transform: 'translateY(-13px)', opacity: 1, offset: 0.85 },
        { transform: 'translateY(0)', opacity: 1, offset: 1 },
      ],
      {
        duration: DOT_DURATION_MS,
        delay: FIRST_DOT_DELAY_MS + index * LETTER_STAGGER_MS * 2,
        easing: 'cubic-bezier(.4, 0, .7, .4)',
        fill: 'both',
      }
    );
  });
}

export function cancelLogoAnimation(logo) {
  ALL_LOGO_IDS.forEach((id) => {
    logo
      .querySelector(`#${id}`)
      .getAnimations()
      .forEach((animation) => animation.cancel());
  });
}

export function showCompletedLogo(logo) {
  ALL_LOGO_IDS.forEach((id) => {
    const part = logo.querySelector(`#${id}`);
    part.style.opacity = 1;
    part.style.transform = 'translate(0)';
  });
}

export function prefersStaticLogo(root) {
  return (
    window.matchMedia('(prefers-reduced-motion: reduce)').matches ||
    root.closest('vividly-presentation')?.hasAttribute('data-capture')
  );
}
