FROM node:20

WORKDIR /app

# Copy dependency files
COPY package.json package-lock.json* ./

# Conditional install based on lockfile presence
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

# Copy remaining source code
COPY . .

# Expose Vite default port
EXPOSE 5173

# Start Vite dev server on all interfaces
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
