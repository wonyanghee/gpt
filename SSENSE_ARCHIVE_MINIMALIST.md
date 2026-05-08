---
name: SSENSE Archive Minimalist
colors:
  background: '#F4F4F5'
  surface-white: '#ffffff'
  text-primary: '#121212'
  text-muted: '#828282'
  border-subtle: '#E2E2E6'
  accent-orange: '#f2520d'
typography:
  display-lg:
    fontFamily: Space Grotesk
    fontSize: 36px
    fontWeight: '700'
    lineHeight: '1.2'
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 20px
    fontWeight: '700'
    lineHeight: '1.2'
  body-md:
    fontFamily: Space Grotesk
    fontSize: 14px
    fontWeight: '500'
    lineHeight: '1.4'
  label-caps:
    fontFamily: Space Grotesk
    fontSize: 10px
    fontWeight: '700'
    lineHeight: '1'
    letterSpacing: 0.1em
  price-tag:
    fontFamily: Space Grotesk
    fontSize: 12px
    fontWeight: '700'
    lineHeight: '1.2'
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  container-max: 1200px
  gutter: 1.5rem
  margin-mobile: 1rem
  margin-desktop: 2.5rem
  stack-sm: 0.5rem
  stack-md: 1.5rem
---

## Brand & Style

The brand personality is **Technical Minimalism**. It draws heavily from high-end fashion editorial aesthetics and technical outdoor apparel branding. The interface is designed to feel like a digital catalog or a gallery space: clinical, precise, and structured.

The design style is a blend of **Modern Minimalism** and **Technical Brutalism**. It prioritizes extreme legibility, high-contrast structural elements, and a utilitarian use of space. There is a "laboratory" feel to the presentation—garments are treated as artifacts within a clean, grid-based system. The primary goal is to provide a neutral backdrop that allows product photography to be the focal point, using stark black accents and sharp borders to define the information hierarchy.

## Colors

The palette is rooted in a monochromatic foundation with a single high-visibility accent.

- **Primary & Neutrals**: The core is built on `#121212` (Ink Black) for text and primary actions, and `#ffffff` (Pure White) for surface containers. The background uses a slightly cool off-white `#F4F4F5` to create subtle separation between the page and the white product cards.
- **Accent**: `#f2520d` (Signal Orange) is used sparingly as a functional highlight, specifically for active states in navigation or tab indicators, nodding to technical/safety gear.
- **Hierarchy**: Text roles are strictly divided between the primary Ink Black and a secondary muted grey `#828282` for metadata, labels, and secondary navigation items.

## Typography

The system utilizes **Space Grotesk** exclusively to maintain a cohesive technical aesthetic.

- **Headlines**: Use heavy weights (Bold 700) with tight letter-spacing for a modern, high-fashion impact.
- **Body**: Set in Medium (500) for better readability at small sizes compared to Regular.
- **Labels**: Utilize "Label Caps" for secondary metadata (like "쇼핑몰 캡처") to create a distinct visual texture that feels like a garment tag or technical specification.
- **Rhythm**: All typography relies on strict vertical alignment and consistent uppercase tracking for navigational elements.

## Layout & Spacing

The layout utilizes a **Fixed Grid** approach for the main content area, centered with a maximum width of 1200px.

- **Sidebar**: A fixed 64px (256px) sidebar on desktop provides a rigid navigational anchor.
- **Grid System**: A responsive multi-column grid (2 cols mobile, 4 cols desktop) with a 24px (1.5rem) gutter.
- **Vertical Rhythm**: Large sections are separated by 40px (2.5rem), while internal card elements are grouped tightly with 8px-12px spacing to emphasize the relationship between image and metadata.
- **Card Aspect Ratio**: All product imagery must adhere to a strict 3:4 aspect ratio to maintain the clinical gallery aesthetic.

## Elevation & Depth

This system rejects shadows and depth in favor of **Structural Outlines** and **Tonal Layering**.

- **Borders**: Depth is communicated via `#E2E2E6` borders. Every functional container (cards, sidebar, header) is defined by a 1px solid stroke.
- **Layering**: The background (`#F4F4F5`) acts as the lowest layer. Active white containers (`#ffffff`) sit on top.
- **Interaction**: Instead of shadows, hover states are communicated through subtle scale transforms on imagery and background color shifts (e.g., button hover turns `#121212` to `#333333`).
- **Overlays**: Labels placed over images use a solid white background with a black border, creating a high-contrast "tag" effect that feels physical rather than digital.

## Shapes

The shape language is primarily **Geometric and Controlled**.

- **Standard Radius**: A base radius of 8px (0.5rem) is used for cards and buttons to soften the brutalist edges just enough for a modern feel.
- **Inner Radius**: Elements within cards (like tags) use a smaller 4px radius or sharp corners to contrast with the outer container.
- **Circular**: Avatars use a full circle crop to provide a singular point of organic contrast against the otherwise rectangular interface.

## Components

- **Primary Button**: Solid `#121212` background, white text, 8px radius, bold typography. No shadow.
- **Cards**: White background, 1px border, 3:4 aspect ratio image. The image should have a `scale(1.05)` transition on hover. Text metadata sits immediately below the container.
- **Tabs**: Horizontal list with 32px spacing. Active state is indicated by a 2px solid bottom border in the `accent-orange` (`#f2520d`) and bold black text. Inactive tabs are muted grey.
- **Tags/Badges**: Small white rectangles with a black border and "Label Caps" typography.
- **Sidebar Nav**: Rounded-lg (8px) background highlights for active items (`#F4F4F5`). Icons use Material Symbols Outlined, set to 20px.
- **Input Fields (System implied)**: Should follow the card style—white background, 1px `#E2E2E6` border, focusing to a 1px `#121212` border.
