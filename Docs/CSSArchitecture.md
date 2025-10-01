# CSS Architecture Standards

## Overview
This document outlines the proper CSS architecture for MediaVortex to ensure maintainability, consistency, and separation of concerns.

## Architecture Principles

### 1. **Centralized CSS Management**
- All common styles are centralized in `Static/css/common.css`
- No inline CSS in individual templates
- Consistent styling across all pages

### 2. **Separation of Concerns**
- **HTML Templates**: Structure and content only
- **CSS Files**: All styling and presentation
- **JavaScript**: Behavior and interactivity

### 3. **DRY Principle (Don't Repeat Yourself)**
- Common styles defined once in `common.css`
- Reusable CSS classes for consistent behavior
- No duplication of styling rules

## File Structure

```
Static/
├── css/
│   └── common.css          # Centralized styles for all pages
Templates/
├── Base.html               # Base template with CSS imports
├── TranscodeQueue.html     # No inline CSS
├── FileScanning.html       # No inline CSS
└── Status.html             # No inline CSS
```

## CSS Organization

### Common.css Structure
```css
/* MediaVortex Common Styles */
/* Centralized CSS for consistent styling across all pages */

/* Table Styling - Common across all pages */
.sortable { ... }
.table-responsive { ... }

/* Button group styling */
.btn-group { ... }

/* Pagination styling */
.pagination { ... }

/* Progress bars */
.scan-progress { ... }

/* Utility classes */
.text-truncate-custom { ... }
```

## Benefits

### ✅ **Maintainability**
- Single source of truth for styles
- Easy to update styling across all pages
- No hunting through multiple template files

### ✅ **Consistency**
- All pages use the same styling rules
- Uniform look and feel
- Reduced visual inconsistencies

### ✅ **Performance**
- CSS is cached by browsers
- Reduced HTML file sizes
- Better separation of concerns

### ✅ **Scalability**
- Easy to add new pages with consistent styling
- Simple to modify global styles
- Clear architecture for team development

## Implementation Rules

### ❌ **DON'T**
- Add `<style>` blocks in individual templates
- Duplicate CSS rules across pages
- Mix CSS with HTML structure
- Create page-specific CSS files

### ✅ **DO**
- Use centralized `common.css` for all styling
- Create reusable CSS classes
- Keep HTML templates clean and focused
- Follow consistent naming conventions

## Migration Process

1. **Identify common styles** across all pages
2. **Move to `common.css`** with proper organization
3. **Remove inline CSS** from individual templates
4. **Update Base.html** to include common CSS
5. **Test all pages** to ensure functionality

## Future Enhancements

### CSS Preprocessing
Consider adding Sass/SCSS for:
- Variables for colors, fonts, spacing
- Mixins for common patterns
- Nested selectors for better organization

### Component-Based CSS
Organize CSS by components:
```css
/* Components */
.btn-group { ... }
.table-responsive { ... }
.progress-bar { ... }

/* Layouts */
.container-fluid { ... }
.row { ... }

/* Utilities */
.text-truncate { ... }
```

## Maintenance Guidelines

1. **Always update `common.css`** for styling changes
2. **Never add inline styles** to templates
3. **Use semantic class names** that describe purpose
4. **Document complex CSS rules** with comments
5. **Test across all pages** after CSS changes

## Compliance with Architecture Standards

This CSS architecture follows:
- **MVVM Pattern**: Clear separation between View (CSS) and ViewModel (JavaScript)
- **Single Responsibility**: Each CSS rule has one purpose
- **Open/Closed Principle**: Easy to extend without modifying existing code
- **DRY Principle**: No duplication of styling rules
- **Separation of Concerns**: CSS handles presentation, HTML handles structure
