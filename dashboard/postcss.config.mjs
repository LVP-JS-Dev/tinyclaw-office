/**
 * PostCSS configuration for Tailwind CSS.
 *
 * This configuration enables Tailwind CSS and Autoprefixer
 * for the Next.js dashboard.
 *
 * @see https://tailwindcss.com/docs/installation/using-postcss
 */

/** @type {import('postcss-load-config').Config} */
const config = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};

export default config;
