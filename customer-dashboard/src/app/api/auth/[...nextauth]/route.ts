import NextAuth from "next-auth"
import AzureADB2CProvider from "next-auth/providers/azure-ad-b2c"
import CredentialsProvider from "next-auth/providers/credentials"

const handler = NextAuth({
  providers: [
    // Azure AD B2C provider (for production)
    ...(process.env.AZURE_AD_B2C_CLIENT_ID ? [
      AzureADB2CProvider({
        tenantId: process.env.AZURE_AD_B2C_TENANT_NAME!,
        clientId: process.env.AZURE_AD_B2C_CLIENT_ID!,
        clientSecret: process.env.AZURE_AD_B2C_CLIENT_SECRET!,
        primaryUserFlow: process.env.AZURE_AD_B2C_PRIMARY_USER_FLOW!,
        authorization: { params: { scope: "openid profile email" } },
      }),
    ] : []),
    // Credentials provider for MVP/pilot
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" }
      },
      async authorize(credentials) {
        // Admin auth
        if (credentials?.email === process.env.ADMIN_EMAIL &&
            credentials?.password === process.env.ADMIN_PASSWORD) {
          return {
            id: "admin",
            email: credentials.email,
            name: "Admin",
            role: "admin"
          }
        }
        // Demo user auth
        if (credentials?.email === process.env.DEMO_EMAIL &&
            credentials?.password === process.env.DEMO_PASSWORD) {
          return {
            id: "demo",
            email: credentials.email,
            name: "Demo User",
            role: "user"
          }
        }
        return null
      }
    })
  ],
  pages: {
    signIn: '/login',
    signOut: '/login',
    error: '/login',
  },
  callbacks: {
    async jwt({ token, user }) {
      if (user) {
        token.role = (user as any).role || 'user'
      }
      return token
    },
    async session({ session, token }) {
      if (session.user) {
        (session.user as any).id = token.sub!
        ;(session.user as any).role = token.role
      }
      return session
    },
  },
  session: {
    strategy: "jwt",
  },
})

export { handler as GET, handler as POST }
