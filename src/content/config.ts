import { defineCollection, z } from 'astro:content';

export const collections = {
	blog: defineCollection({
		schema: z.object({
			title: z.string(),
			description: z.string(),
			lang: z.enum(['en', 'pt', 'es']).default('en'),
			// Shared by every translation of the same post.
			key: z.string().optional(),
			publishDate: z.coerce.date(),
			tags: z.array(z.string()),
			repo: z.string().url().optional(),
			cover: z.string().optional(),
			cover_alt: z.string().optional(),
		}),
	}),
};
