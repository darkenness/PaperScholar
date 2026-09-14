/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {source:'/uploads/:path*',destination:`${process.env.BACKEND_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/uploads/:path*`},
      {
        source: '/api/:path*',
        destination: `${process.env.BACKEND_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
