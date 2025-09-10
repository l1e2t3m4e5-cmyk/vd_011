# replit.md

## Overview

This is a modern Flask-based web application that allows users to download videos from various platforms using yt-dlp (YouTube downloader). The application features a sleek, responsive UI built with pure HTML, CSS, and minimal JavaScript. Users can paste or drag-and-drop video URLs, fetch available formats, and download videos with enhanced real-time progress tracking including speed, ETA, and percentage completion. The system uses threading for background downloads and maintains task state in memory.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Backend Architecture
- **Framework**: Flask web framework serving as the main application server
- **Download Engine**: yt-dlp library for video extraction and downloading from multiple platforms
- **Task Management**: In-memory dictionary-based task tracking with UUID generation for unique task identification
- **Concurrency**: Threading module for handling background download operations without blocking the main application
- **File Storage**: Local filesystem storage in a dedicated downloads folder

### Frontend Architecture
- **Template Engine**: Flask's built-in Jinja2 templating for HTML rendering
- **Styling**: Modern CSS3 with custom properties, CSS Grid, Flexbox, and smooth animations
- **JavaScript**: Minimal vanilla JavaScript for API calls, DOM updates, and drag-and-drop functionality
- **Theme Support**: Dynamic light/dark theme toggle using CSS custom properties with localStorage persistence
- **Responsive Design**: Mobile-first approach with touch-friendly controls and adaptive layouts
- **User Experience**: Drag-and-drop URL input, clipboard paste functionality, and CSS-only loading animations

### Data Flow
- **Task Lifecycle**: Tasks progress through states: queued → downloading → completed/error
- **Progress Tracking**: Real-time download progress via progress hooks and AJAX polling
- **Format Selection**: Dynamic format fetching allows users to choose quality/format before download
- **File Management**: Downloaded files are stored locally with systematic naming and cleanup

### API Design
- **RESTful Endpoints**: JSON-based API for format fetching, download initiation, and status checking
- **Progress Hooks**: Custom progress callback functions for real-time download statistics
- **Error Handling**: Comprehensive exception handling with user-friendly error messages

## External Dependencies

### Core Libraries
- **yt-dlp**: Primary video downloading library supporting multiple platforms
- **Flask**: Web framework for HTTP request handling and templating
- **Bootstrap**: CSS framework for responsive UI components

### System Dependencies
- **Threading**: Python standard library for concurrent download operations
- **UUID**: Standard library for unique task identifier generation
- **OS/Filesystem**: Local file system for download storage and management

### Browser Requirements
- **Modern JavaScript**: ES6+ features for client-side functionality
- **Fetch API**: For asynchronous HTTP requests to backend endpoints
- **CSS Grid/Flexbox**: For responsive layout rendering