import Navbar from "@/components/navbar";
import Hero from "@/components/hero";
import Ticker from "@/components/ticker";
import Features from "@/components/features";
import HowItWorks from "@/components/how-it-works";
import GetStarted from "@/components/get-started";
import FAQ from "@/components/faq";
import Footer from "@/components/footer";
import ScrollToTop from "@/components/scroll-to-top";
import FadeIn from "@/components/fade-in";

export default function Home() {
  return (
    <>
      <Navbar />
      <main>
        <Hero />
        <Ticker />
        <FadeIn>
          <Features />
        </FadeIn>
        <FadeIn delay={0.05}>
          <HowItWorks />
        </FadeIn>
        <FadeIn delay={0.05}>
          <GetStarted />
        </FadeIn>
        <FadeIn delay={0.05}>
          <FAQ />
        </FadeIn>
      </main>
      <FadeIn>
        <Footer />
      </FadeIn>
      <ScrollToTop />
    </>
  );
}
