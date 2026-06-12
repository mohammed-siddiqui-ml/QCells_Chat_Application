# Frontend Setup Guide

## Overview
React 18.2 application built with Vite 5.0 and TypeScript 5.3 for the GenAI Intelligent Chat-Based Knowledge Retrieval System.

## Technology Stack

### Core
- **React**: 18.2.0
- **TypeScript**: 5.3.3
- **Vite**: 5.0.12

### UI Framework
- **Material-UI**: 5.14.20
- **Emotion**: 11.11.3 (CSS-in-JS)

### State Management & Data Fetching
- **React Query**: 5.0.5 (@tanstack/react-query)
- **React Router**: 6.21.3

### Communication
- **Socket.io Client**: 4.6.2
- **Axios**: 1.6.7

### Utilities
- **date-fns**: 3.3.1

## Installation

1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

## Available Scripts

- `npm run dev` - Start development server on http://localhost:3000
- `npm run build` - Build for production
- `npm run preview` - Preview production build
- `npm run lint` - Run ESLint
- `npm run format` - Format code with Prettier
- `npm run type-check` - Run TypeScript type checking

## Configuration

### Vite Configuration
- **Dev Server**: Port 3000
- **API Proxy**: `/api` → `http://localhost:8000`
- **Path Aliases**: Configured for all module directories

### TypeScript Configuration
- **Strict Mode**: Enabled
- **Path Aliases**: Configured for @/components, @/pages, etc.
- **Target**: ES2020

### ESLint & Prettier
- **Style Guide**: Airbnb + TypeScript
- **Line Length**: 100 characters
- **Prettier Integration**: Enabled

## Directory Structure

```
src/
├── components/     # Reusable React components
│   ├── Admin/      # Admin-specific components
│   ├── Chat/       # Chat interface components
│   └── Common/     # Shared components
├── pages/          # Page-level components (routes)
├── services/       # API clients and external services
├── hooks/          # Custom React hooks
├── context/        # React Context providers
├── utils/          # Utility functions
└── types/          # TypeScript type definitions
```

## Development Workflow

1. Start the development server:
   ```bash
   npm run dev
   ```

2. Make changes to the code

3. Format and lint:
   ```bash
   npm run format
   npm run lint
   ```

4. Type check:
   ```bash
   npm run type-check
   ```

5. Build for production:
   ```bash
   npm run build
   ```

## Environment Requirements
- **Node.js**: >=18.0.0
- **npm**: >=9.0.0

## Notes
- The backend API should be running on port 8000
- All API calls are proxied through `/api` endpoint
- Path aliases are configured for cleaner imports
