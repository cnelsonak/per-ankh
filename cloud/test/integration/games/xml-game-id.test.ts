// Exercises xml_game_id exposure across every game-list/detail surface
// (cloud/src/games.ts): GET /v1/games, GET /v1/games/:id,
// GET /v1/games/out-of-date, and GET /v1/admin/games/out-of-date. See
// docs/elo-calculator-design.md § "Match Deduplication via xml_game_id --
// Verified Feasible" for why the field exists and how it's used.

import { applyD1Migrations, env } from "cloudflare:test";
import { beforeAll, describe, expect, it } from "vitest";
import { nanoid } from "nanoid";
import { expectOk } from "../../helpers/assertions";
import { makeSiteAdmin, makeUser, type TestUser } from "../../helpers/builders";
import { seedGame } from "../../helpers/games";
import { request } from "../../helpers/requests";

beforeAll(async () => {
	await applyD1Migrations(env.SHARE_DB, env.TEST_MIGRATIONS);
});

async function seedStaleGame(
	user: TestUser,
	parserVersion: string,
	xmlGameId: string,
): Promise<string> {
	const gameId = nanoid(21);
	await env.SHARE_DB.prepare(
		`INSERT INTO games (
			game_id, user_id, xml_game_id, total_turns, file_hash,
			is_public, blob_version, blob_size_bytes, parser_version
		) VALUES (?, ?, ?, 50, ?, 0, 2, 1024, ?)`,
	)
		.bind(gameId, user.userId, xmlGameId, nanoid(64), parserVersion)
		.run();
	return gameId;
}

async function setXmlGameId(gameId: string, xmlGameId: string): Promise<void> {
	await env.SHARE_DB.prepare(
		`UPDATE games SET xml_game_id = ? WHERE game_id = ?`,
	)
		.bind(xmlGameId, gameId)
		.run();
}

interface DetailBody {
	xml_game_id: string;
}

interface ListBody {
	games: { game_id: string; xml_game_id: string }[];
}

describe("xml_game_id on GET /v1/games and GET /v1/games/:id", () => {
	it("is present on the game-detail response", async () => {
		const owner = await makeUser();
		const gameId = await seedGame(owner, { isPublic: true });
		await setXmlGameId(gameId, "8a378aa9-cfd6-4ce6-b18e-3709c9043d27");

		const body = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${gameId}` }),
		);

		expect(body.xml_game_id).toBe("8a378aa9-cfd6-4ce6-b18e-3709c9043d27");
	});

	it("is present on each row of the game-list response", async () => {
		const owner = await makeUser();
		const gameId = await seedGame(owner, { isPublic: true });
		await setXmlGameId(gameId, "15443b64-8934-4ce4-8bd9-4333b6663280");

		const body = await expectOk<ListBody>(
			await request.get({ path: `/v1/games?user_id=${owner.userId}` }),
		);

		const row = body.games.find((g) => g.game_id === gameId);
		expect(row?.xml_game_id).toBe("15443b64-8934-4ce4-8bd9-4333b6663280");
	});

	it("demonstrates the actual dedup use case: two separate uploads of the same underlying game share xml_game_id", async () => {
		// Two different accounts, each uploading their own perspective's save
		// from the same multiplayer session -- exactly the scenario that
		// currently can't be reconciled via the public API.
		const playerA = await makeUser();
		const playerB = await makeUser();
		const sharedGameId = "b80213c0-d26b-4616-8534-53ab956ca22a";

		const uploadFromA = await seedGame(playerA, { isPublic: true });
		const uploadFromB = await seedGame(playerB, { isPublic: true });
		await setXmlGameId(uploadFromA, sharedGameId);
		await setXmlGameId(uploadFromB, sharedGameId);

		const detailA = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${uploadFromA}` }),
		);
		const detailB = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${uploadFromB}` }),
		);

		expect(detailA.xml_game_id).toBe(sharedGameId);
		expect(detailB.xml_game_id).toBe(sharedGameId);
	});

	it("is distinct across genuinely different games from the same uploader", async () => {
		const uploader = await makeUser();

		const firstGame = await seedGame(uploader, { isPublic: true });
		const secondGame = await seedGame(uploader, { isPublic: true });
		await setXmlGameId(firstGame, "game-one");
		await setXmlGameId(secondGame, "game-two");

		const detail1 = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${firstGame}` }),
		);
		const detail2 = await expectOk<DetailBody>(
			await request.get({ path: `/v1/games/${secondGame}` }),
		);

		expect(detail1.xml_game_id).not.toBe(detail2.xml_game_id);
	});
});

describe("xml_game_id on GET /v1/games/out-of-date", () => {
	it("is present on each row", async () => {
		const user = await makeUser();
		const gameId = await seedStaleGame(
			user,
			"2.5.0",
			"71e0b0b6-4f8a-4b1a-9c3e-1a2b3c4d5e6f",
		);

		const body = await expectOk<ListBody>(
			await request.get({
				path: "/v1/games/out-of-date?version=3.0.0",
				as: user,
			}),
		);

		const row = body.games.find((g) => g.game_id === gameId);
		expect(row?.xml_game_id).toBe("71e0b0b6-4f8a-4b1a-9c3e-1a2b3c4d5e6f");
	});
});

describe("xml_game_id on GET /v1/admin/games/out-of-date", () => {
	it("is present on each row", async () => {
		const admin = await makeSiteAdmin();
		const owner = await makeUser();
		const gameId = await seedStaleGame(
			owner,
			"2.5.0",
			"9c8b7a6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d",
		);

		const body = await expectOk<ListBody>(
			await request.get({
				path: "/v1/admin/games/out-of-date?version=3.0.0",
				as: admin,
			}),
		);

		const row = body.games.find((g) => g.game_id === gameId);
		expect(row?.xml_game_id).toBe("9c8b7a6d-5e4f-3a2b-1c0d-9e8f7a6b5c4d");
	});
});
