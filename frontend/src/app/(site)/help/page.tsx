import type { Metadata } from "next";
import Link from "next/link";

import { PageHero, Prose } from "@/components/site/marketing";

export const metadata: Metadata = { title: "Help center" };

export default function HelpPage() {
  return (
    <>
      <PageHero title="Help center" description="Guides for getting the most out of Virello Studio." />
      <Prose>
        <h2>Uploading a video</h2>
        <p>
          From your dashboard, choose <strong>New project</strong> or drop a file onto the upload area. MP4, MOV and WebM are supported.
          Keep the tab open until the upload reaches 100%; you can cancel at any time and retry if your connection drops.
        </p>
        <h2>Why is my video still processing?</h2>
        <p>
          After upload we verify the file, read its details and create a thumbnail. The project page shows the current stage. Larger
          files take longer to inspect. If a step fails, the page explains why and offers a retry when it is safe.
        </p>
        <h2>Creating and editing clips</h2>
        <ul>
          <li>Open a ready project and choose <strong>New clip</strong>.</li>
          <li>Play the source, then use <strong>Set start</strong> and <strong>Set end</strong> at the playhead, or type exact times.</li>
          <li>Pick a format (9:16, 1:1 or 16:9) and drag the crop slider to keep your subject in frame.</li>
          <li>Changes are saved to your project. Undo and redo are available while you edit.</li>
        </ul>
        <h2>Exporting</h2>
        <p>
          Choose <strong>Render</strong>. Rendering happens on our servers, so you can leave the page. When it finishes, preview the clip and
          download the MP4. If you change a clip after rendering, render again to update the export.
        </p>
        <h2>Usage and limits</h2>
        <p>
          Your <Link href="/usage">usage page</Link> lists every minute counted this month. Failed and cancelled jobs are never charged.
        </p>
        <h2>Deleting your data</h2>
        <p>
          You can delete exports, projects or your whole account from inside the app. Deletion removes the stored media immediately.
        </p>
        <h2>Still stuck?</h2>
        <p>
          <Link href="/contact">Contact us</Link> and include the reference ID shown with any error message.
        </p>
      </Prose>
    </>
  );
}
