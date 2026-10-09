import type { LucideIcon } from "lucide-react";
import { Captions, Crop, Download, Gauge, Layers, ScanSearch, Scissors, ShieldCheck, Sparkles, UploadCloud, Wand2, Share2 } from "lucide-react";

export interface Feature {
  icon: LucideIcon;
  title: string;
  description: string;
  available: boolean;
}

/** Feature availability is kept honest: only shipped features are marked available. */
export const FEATURES: Feature[] = [
  { icon: UploadCloud, title: "Direct, resumable-friendly uploads", description: "Send MP4, MOV or WebM files straight to private storage with real progress, cancel and retry.", available: true },
  { icon: ScanSearch, title: "Automatic video inspection", description: "Every upload is verified and inspected for duration, resolution, frame rate and audio before you edit.", available: true },
  { icon: Scissors, title: "Precise trim editor", description: "Scrub the source, set in and out points to a tenth of a second, and save as many clips as you need.", available: true },
  { icon: Crop, title: "Reframe for every platform", description: "Export 9:16, 1:1 or 16:9. Slide the crop window to keep your subject in frame, or fit the full shot with padding.", available: true },
  { icon: Download, title: "Platform-ready MP4 exports", description: "H.264/AAC files with fast-start metadata, rendered server side and validated before they reach you.", available: true },
  { icon: Gauge, title: "Live processing status", description: "See each real processing stage as it happens. Failed jobs explain why and can be retried safely.", available: true },
  { icon: Sparkles, title: "AI viral shorts", description: "Pick 30 seconds or 1 minute and AI finds self-contained moments in your video, explains each pick, and renders them as vertical shorts.", available: true },
  { icon: Captions, title: "Captions and subtitles", description: "Captions from an editable AI transcript, burned into your shorts or downloaded as SRT and VTT.", available: true },
  { icon: Wand2, title: "Subject-aware reframing", description: "Smooth, automatic crop tracking that follows the speaker, with center crop as a safe fallback.", available: false },
  { icon: Layers, title: "Brand templates", description: "Save caption styles, colors and logos once and apply them to every clip.", available: false },
  { icon: Share2, title: "Publishing integrations", description: "Post to supported platforms through their official APIs once app approvals are in place.", available: false },
  { icon: ShieldCheck, title: "Private by default", description: "Media lives in private storage and is only reachable through short-lived signed links.", available: true },
];

export const STEPS = [
  { title: "Upload your long video", description: "Drop in a podcast, webinar, interview or lesson. We store it privately and inspect it automatically." },
  { title: "Choose your moments", description: "Scrub the timeline, mark the start and end of each clip, and pick the format for every destination." },
  { title: "Export and post", description: "Render platform-ready MP4s in the background, preview them, and download when they are ready." },
];

export const USE_CASES = [
  { title: "Creators", description: "Turn long streams and vlogs into a steady stream of vertical shorts." },
  { title: "Podcasters", description: "Pull standout exchanges from every episode and share them where listeners scroll." },
  { title: "Educators", description: "Cut lectures and tutorials into focused, single-idea lessons." },
  { title: "Marketers", description: "Repurpose webinars and product demos into campaign-ready social clips." },
  { title: "Businesses", description: "Share leadership updates, events and customer stories in every format." },
];

export const FAQS = [
  { q: "What does Virello Studio do today?", a: "Upload a long video and choose 30-second or 1-minute shorts: AI transcribes it, picks self-contained moments, and renders vertical clips with captions. You can also trim, reframe to 9:16, 1:1 or 16:9, edit the transcript, and export MP4, SRT and VTT files." },
  { q: "Which file types can I upload?", a: "MP4, MOV and WebM. Files are checked by their actual content, not just their extension. Size and length limits depend on your plan and are shown before you upload." },
  { q: "Does Virello guarantee my clips will go viral?", a: "No. No tool can guarantee views. AI scores are estimates to help you choose between moments, not predictions of performance." },
  { q: "How is usage counted?", a: "Source minutes are counted once when a video is processed successfully, and render minutes are counted per successful export by clip length. Failed and cancelled jobs are never charged. Your usage page shows every entry." },
  { q: "Who can see my videos?", a: "Only you. Media is stored in private storage and served through links that expire within minutes. You can delete individual exports, whole projects, or your entire account at any time." },
  { q: "Will you use my videos to train AI models?", a: "We don't. For AI shorts, your video's audio is sent to Google's Gemini API only to transcribe it and pick moments, under Google's API data terms. See the privacy policy for details." },
  { q: "Can I import from a YouTube or social media link?", a: "Not at the moment. Many platforms do not permit downloading through third-party tools, so direct upload of files you have rights to is the supported method." },
  { q: "How do paid plans work?", a: "Plans differ by monthly minutes, upload size and video length. Online checkout is not available yet; the pricing page shows each plan's limits today." },
];
