// Shared motion animation variants and transition presets.

import type { Variants, Transition } from "motion/react";

/** Fade in from transparent. */
export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1 },
};

/** Slide up with fade for page/card entrance. */
export const slideUp: Variants = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0 },
};

/** Staggered container -- children animate in sequence. */
export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.05,
    },
  },
};

/** Page-level crossfade for view transitions. */
export const pageFade: Variants = {
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
};

/** Spring transition for snappy UI elements. */
export const springTransition: Transition = {
  type: "spring",
  stiffness: 500,
  damping: 30,
};

/** Default enter/exit transition. */
export const defaultTransition: Transition = {
  duration: 0.2,
  ease: "easeOut",
};
