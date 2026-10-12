const docs = "https://github.com/ashworks1706/louped/blob/main/docs";

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  // the docs are Markdown in the repository now; old links (PyPI, published READMEs) go there
  async redirects() {
    return [
      { source: "/docs", destination: `${docs}/README.md`, permanent: true },
      { source: "/docs/:page", destination: `${docs}/:page.md`, permanent: true },
    ];
  },
};

export default config;
