export { default } from "next-auth/middleware";

export const config = {
  matcher: ["/markets/:path*", "/simulator/:path*", "/settings/:path*", "/import/:path*"],
};
