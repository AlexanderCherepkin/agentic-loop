package main

import (
	"html/template"
	"log"
	"os"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/logger"
	"github.com/joho/godotenv"
)

func main() {
	_ = godotenv.Load()

	db, err := InitDB()
	if err != nil {
		log.Fatalf("failed to init db: %v", err)
	}

	engine := template.Must(template.ParseGlob("templates/*"))
	app := fiber.New(fiber.Config{
		Views: engine,
	})
	app.Use(logger.New())

	app.Static("/static", "./static")

	authHandler := NewAuthHandler(db)
	authHandler.RegisterRoutes(app)

	app.Get("/", func(c *fiber.Ctx) error {
		return c.Render("index", fiber.Map{"User": c.Locals("user")})
	})

	app.Get("/health", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{"status": "ok"})
	})

	app.Get("/me", JWTMiddleware(), func(c *fiber.Ctx) error {
		user := c.Locals("user").(*User)
		return c.JSON(user)
	})

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	log.Fatal(app.Listen(":" + port))
}
