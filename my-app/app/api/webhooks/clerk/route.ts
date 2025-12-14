import { Webhook } from "svix";
import { WebhookEvent } from "@clerk/nextjs/server";
import prisma from "@/lib/prisma";
import { NextResponse } from "next/server";

export async function POST(req: Request) {
  try {
    const WEBHOOK_SECRET = process.env.CLERK_WEBHOOK_SIGNING_SECRET;
    console.log(WEBHOOK_SECRET);

    if (!WEBHOOK_SECRET) {
      throw new Error(
        "Please add WEBHOOK_SECRET from Clerk Dashboard to .env or .env.local"
      );
    }

    const headerPayload = req.headers;
    console.log(headerPayload);
    const svix_id = headerPayload.get("svix-id");
    const svix_timestamp = headerPayload.get("svix-timestamp");
    const svix_signature = headerPayload.get("svix-signature");
    console.log(`${svix_id}, ${svix_timestamp}, ${svix_signature}`);

    if (!svix_id || !svix_timestamp || !svix_signature) {
      return new Response("Error occurred -- no svix headers", {
        status: 400,
      });
    }

    const payload = await req.json();
    const body = JSON.stringify(payload);

    const wh = new Webhook(WEBHOOK_SECRET);
    let event: WebhookEvent;

    try {
      event = wh.verify(body, {
        "svix-id": svix_id,
        "svix-timestamp": svix_timestamp,
        "svix-signature": svix_signature,
      }) as WebhookEvent;
      console.log(event);
    } catch (err) {
      console.error("Error verifying webhook:", err);
      return new Response("Error occurred", {
        status: 400,
      });
    }
    console.log(event.data);
    console.log(`Received webhook with event type of ${event.type}`);
    if (event.type === "user.created") {
      const {
        id,
        email_addresses,
        primary_email_address_id,
      } = event.data;
      const emailObj = email_addresses.find(
        (email) => email.id === primary_email_address_id
      );
      const email = emailObj?.email_address;

      // ✅ FIX: Handle undefined email
      if (!email) {
        throw new Error("Primary email not found for user creation");
      }

      await prisma.user.create({
        data: {
          id,
          email, // Now guaranteed to be string
        },
      });
    } else if (event.type === "user.updated") {
      const {
        id,
        email_addresses,
        primary_email_address_id,
      } = event.data;
      const emailObj = email_addresses.find(
        (email) => email.id === primary_email_address_id
      );
      const email = emailObj?.email_address;

      // ✅ FIX: Handle undefined email
      if (!email) {
        throw new Error("Primary email not found for user update");
      }

      await prisma.user.update({
        where: {
          id,
        },
        data: {
          email, // Now guaranteed to be string
        },
      });
    } else if (event.type === "user.deleted") {
      const { id } = event.data;
      await prisma.user.deleteMany({
        where: {
          id,
        },
      });
    }
    return NextResponse.json({ message: "Success" }, { status: 200 });
  } catch (err) {
    console.error("WEBHOOK_ERROR:", err);
    return NextResponse.json({ error: JSON.stringify(err) }, { status: 400 });
  }
}